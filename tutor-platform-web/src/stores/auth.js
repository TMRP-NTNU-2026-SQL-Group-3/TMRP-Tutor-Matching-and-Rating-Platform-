import axios from 'axios'
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useMatchStore } from './match'
import { useMessageStore } from './message'
import { useTutorStore } from './tutor'
import { useToastStore } from './toast'
import { API_BASE_URL } from '@/api/baseURL'
import { resetRefreshState, markLoggedIn } from '@/api'

export const useAuthStore = defineStore('auth', () => {
  // SEC-C02: tokens are now in HttpOnly cookies — JS never touches them.
  // Only user info (non-sensitive) is persisted in localStorage for
  // cross-tab / page-refresh continuity.
  // One-time cleanup: remove stale token entries from the pre-cookie era.
  localStorage.removeItem('token')
  localStorage.removeItem('refreshToken')

  let savedUser = null
  try { savedUser = JSON.parse(localStorage.getItem('user') || 'null') } catch { /* corrupted */ }
  const user = ref(savedUser)

  const isLoggedIn = computed(() => !!user.value)
  const role = computed(() => user.value?.role || '')

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
    // F-06: drop the loggingOut fence (raised by a previous logout) now that a
    // fresh session is in place, so 401s on the new user's requests can refresh.
    markLoggedIn()
  }

  function logout() {
    user.value = null
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

  return { user, isLoggedIn, role, setAuth, logout }
})
