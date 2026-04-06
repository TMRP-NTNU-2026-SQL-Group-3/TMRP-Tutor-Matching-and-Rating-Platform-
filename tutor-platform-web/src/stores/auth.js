import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

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
    token.value = ''
    refreshToken.value = ''
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('refreshToken')
    localStorage.removeItem('user')
  }

  return { token, refreshToken, user, isLoggedIn, role, setAuth, logout }
})
