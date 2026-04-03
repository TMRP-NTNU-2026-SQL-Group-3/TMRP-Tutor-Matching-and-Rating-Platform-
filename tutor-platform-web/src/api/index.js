import axios from 'axios'
import { useAuthStore } from '@/stores/auth'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 30000,
})

// Request Interceptor：自動附加 JWT Token
api.interceptors.request.use(config => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

// Response Interceptor：統一解包回應
api.interceptors.response.use(
  response => {
    const { success, data, message } = response.data
    if (!success) {
      return Promise.reject(new Error(message))
    }
    return data
  },
  error => {
    if (error.response?.status === 401) {
      const auth = useAuthStore()
      auth.logout()
      window.location.href = '/login'
    }
    const message = error.response?.data?.message || '網路連線異常'
    return Promise.reject(new Error(message))
  }
)

export default api
