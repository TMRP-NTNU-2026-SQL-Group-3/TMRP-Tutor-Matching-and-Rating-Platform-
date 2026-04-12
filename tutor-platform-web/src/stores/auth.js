import axios from 'axios'
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useMatchStore } from './match'
import { useMessageStore } from './message'
import { useTutorStore } from './tutor'
import { API_BASE_URL } from '@/api/baseURL'

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
    // 使用原始 axios 而非 api instance，因為 store 的 token 已清除，
    // 攔截器無法再附上 Authorization header；改以保留下來的 savedToken 直接帶。
    // baseURL 由 @/api 集中定義，避免與 axios instance 的 baseURL 漂移（Bug #19）。
    if (savedRefreshToken && savedToken) {
      axios.post(`${API_BASE_URL}/api/auth/logout`, { refresh_token: savedRefreshToken }, {
        headers: { Authorization: `Bearer ${savedToken}` }
      }).catch(() => {})
    }
  }

  return { token, refreshToken, user, isLoggedIn, role, setAuth, logout }
})
