import axios from 'axios'
import { useAuthStore } from '@/stores/auth'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 30000,
})

let isRefreshing = false
let pendingRequests = []

// P-BIZ-02: 傳入第二個參數 null 表示無錯誤，與排隊 callback 簽名一致
function onRefreshed(newToken) {
  pendingRequests.forEach((cb) => cb(newToken, null))
  pendingRequests = []
}

// Request Interceptor：自動附加 JWT Token
api.interceptors.request.use(config => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

// Response Interceptor：統一解包回應 + refresh token 流程 + 自動重試
api.interceptors.response.use(
  response => {
    const body = response.data
    if (body === undefined || body === null || typeof body !== 'object' || !('success' in body)) {
      return body
    }
    const { success, data, message } = body
    if (!success) {
      return Promise.reject(new Error(message || '操作失敗'))
    }
    return data
  },
  async error => {
    const originalConfig = error.config

    // 401 — 嘗試用 refresh token 取得新的 access token
    if (error.response?.status === 401 && !originalConfig._retry) {
      const auth = useAuthStore()

      if (auth.refreshToken) {
        if (isRefreshing) {
          // 已在刷新中，排隊等待
          return new Promise((resolve, reject) => {
            pendingRequests.push((newToken, error) => {
              if (error) return reject(error)
              originalConfig._retry = true
              originalConfig.headers.Authorization = `Bearer ${newToken}`
              resolve(api.request(originalConfig))
            })
          })
        }

        originalConfig._retry = true
        isRefreshing = true

        try {
          const res = await axios.post(
            `${api.defaults.baseURL}/api/auth/refresh`,
            { refresh_token: auth.refreshToken }
          )
          const { access_token, refresh_token, user_id, role, display_name } = res.data.data
          auth.setAuth(access_token, { user_id, role, display_name }, refresh_token)
          onRefreshed(access_token)
          originalConfig.headers.Authorization = `Bearer ${access_token}`
          return api.request(originalConfig)
        } catch (refreshError) {
          pendingRequests.forEach((cb) => cb(null, refreshError))
          pendingRequests = []
          auth.logout()
          window.location.href = '/login'
          return Promise.reject(refreshError)
        } finally {
          isRefreshing = false
        }
      }

      auth.logout()
      window.location.href = '/login'
      return Promise.reject(error)
    }

    // 5xx 或網路錯誤 — 指數退避重試（最多 2 次）
    const retryCount = originalConfig._retryCount || 0
    const isRetryable = !error.response || error.response.status >= 500 || error.code === 'ECONNABORTED'
    if (isRetryable && retryCount < 2) {
      originalConfig._retryCount = retryCount + 1
      await new Promise((r) => setTimeout(r, 1000 * 2 ** retryCount))
      return api.request(originalConfig)
    }

    let message = '網路連線異常'
    if (error.response?.data instanceof Blob) {
      try {
        const text = await error.response.data.text()
        const json = JSON.parse(text)
        message = json.message || message
      } catch { /* ignore parse errors */ }
    } else {
      message = error.response?.data?.message || message
    }
    return Promise.reject(new Error(message))
  }
)

export default api
