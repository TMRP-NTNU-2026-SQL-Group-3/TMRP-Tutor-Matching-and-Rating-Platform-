import axios from 'axios'
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useMatchStore } from './match'
import { useMessageStore } from './message'
import { useTutorStore } from './tutor'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const refreshToken = ref(localStorage.getItem('refreshToken') || '')

  let savedUser = null
  try { savedUser = JSON.parse(localStorage.getItem('user') || 'null') } catch { /* corrupted */ }
  const user = ref(savedUser)

  const isLoggedIn = computed(() => !!token.value && !!user.value)
  const role = computed(() => user.value?.role || '')

  function setAuth(tokenValue, userData, refreshTokenValue) {
    token.value = tokenValue
    user.value = userData
    localStorage.setItem('token', tokenValue)
    localStorage.setItem('user', JSON.stringify(userData))
    if (refreshTokenValue !== undefined) {
      refreshToken.value = refreshTokenValue
      localStorage.setItem('refreshToken', refreshTokenValue)
    }
  }

  function logout() {
    // P-BIZ-01: 先保存 token 與 refresh token，清除本地狀態，再非同步撤銷
    const savedToken = token.value
    const savedRefreshToken = refreshToken.value

    token.value = ''
    refreshToken.value = ''
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('refreshToken')
    localStorage.removeItem('user')

    // 清除其他 store 的快取資料，避免下一位登入使用者看到前一位的敏感資料
    useMatchStore().setMatches([])
    useMessageStore().setConversations([])
    const tutorStore = useTutorStore()
    tutorStore.setResults([])
    tutorStore.setFilters({})

    // P-BIZ-01: 非同步撤銷 refresh token（fire-and-forget，不阻塞登出流程）
    // 使用原始 axios 而非 api instance，因為 store 的 token 已清除
    if (savedRefreshToken && savedToken) {
      const baseURL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
      axios.post(`${baseURL}/api/auth/logout`, { refresh_token: savedRefreshToken }, {
        headers: { Authorization: `Bearer ${savedToken}` }
      }).catch(() => {})
    }
  }

  return { token, refreshToken, user, isLoggedIn, role, setAuth, logout }
})
