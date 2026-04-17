import axios from 'axios'
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useMatchStore } from './match'
import { useMessageStore } from './message'
import { useTutorStore } from './tutor'
import { useToastStore } from './toast'
import { API_BASE_URL } from '@/api/baseURL'
import api, { resetRefreshState, markLoggedIn } from '@/api'

export const useAuthStore = defineStore('auth', () => {
  // SEC-C02: tokens are now in HttpOnly cookies — JS never touches them.
  // Only user info (non-sensitive) is persisted in localStorage for
  // cross-tab / page-refresh continuity.
  // One-time cleanup: remove stale token entries from the pre-cookie era.
  localStorage.removeItem('token')
  localStorage.removeItem('refreshToken')

  // MEDIUM-4: localStorage is treated as a CACHE ONLY. Router guards must
  // await `ensureVerified()` before trusting `role` for any authorization
  // decision — an XSS primitive or a browser extension can freely overwrite
  // localStorage.user, so the authoritative role comes from /api/auth/me
  // (which is gated by the HttpOnly auth cookie the attacker cannot forge).
  let savedUser = null
  try { savedUser = JSON.parse(localStorage.getItem('user') || 'null') } catch { /* corrupted */ }
  const user = ref(savedUser)
  const verified = ref(false)
  let verifyPromise = null

  const isLoggedIn = computed(() => !!user.value)
  const role = computed(() => user.value?.role || '')

  async function ensureVerified() {
    if (verified.value) return user.value
    if (verifyPromise) return verifyPromise
    verifyPromise = (async () => {
      try {
        // api interceptor unwraps the envelope — `data` is the payload object.
        const data = await api.get('/api/auth/me')
        // Backend returns full user record; narrow to the fields the store trusts.
        const { user_id, role: serverRole, display_name } = data || {}
        if (!user_id || !VALID_ROLES.includes(serverRole)) {
          throw new Error('invalid /me payload')
        }
        const authoritative = { user_id, role: serverRole, display_name }
        user.value = authoritative
        localStorage.setItem('user', JSON.stringify(authoritative))
        verified.value = true
        return authoritative
      } catch (err) {
        // Any failure (401 after failed refresh, network, bad payload) → no session.
        // Do NOT call logout() here; that would trigger a redirect and reset
        // stores while the router guard is still running. The guard reads
        // user.value after us and routes to /login on falsy.
        user.value = null
        localStorage.removeItem('user')
        verified.value = false
        throw err
      } finally {
        verifyPromise = null
      }
    })()
    return verifyPromise
  }

  const VALID_ROLES = ['parent', 'tutor', 'admin']

  function setAuth(userData) {
    // Guard against an upstream bug (e.g. a broken interceptor) writing a
    // bogus role into the store — router guards and UI gates all key off
    // `user.role`, so silently accepting anything here masks the real bug.
    if (!userData || typeof userData !== 'object') {
      throw new Error('setAuth: userData must be an object')
    }
    if (!VALID_ROLES.includes(userData.role)) {
      throw new Error(`setAuth: invalid role "${userData.role}"`)
    }
    user.value = userData
    localStorage.setItem('user', JSON.stringify(userData))
    // MEDIUM-4: setAuth is only called by login and by the refresh handler,
    // both of which received the role from the server — mark verified so we
    // don't bounce the user back through /auth/me on the next navigation.
    verified.value = true
    // F-06: drop the loggingOut fence (raised by a previous logout) now that a
    // fresh session is in place, so 401s on the new user's requests can refresh.
    markLoggedIn()
  }

  function logout() {
    user.value = null
    verified.value = false
    localStorage.removeItem('user')

    // Clear other stores to prevent the next user from seeing stale data.
    useMatchStore().setMatches([])
    useMessageStore().setConversations([])
    const tutorStore = useTutorStore()
    tutorStore.setResults([])
    tutorStore.setFilters({})
    useToastStore().clear()

    // Drop any pending token-refresh from the previous session so it cannot
    // resolve into the next user's request stream.
    resetRefreshState()

    // SEC-C02: fire-and-forget backend logout. HttpOnly cookies are sent
    // automatically; the server clears them via Set-Cookie in the response.
    axios.post(`${API_BASE_URL}/api/auth/logout`, null, {
      withCredentials: true,
    }).catch(() => {})
  }

  return { user, isLoggedIn, role, verified, ensureVerified, setAuth, logout }
})
