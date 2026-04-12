import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import { API_BASE_URL } from './baseURL'

// 重新導出，方便外部維持 `import { API_BASE_URL } from '@/api'` 的舊用法
export { API_BASE_URL }

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
})

// P-BIZ-02 / Bug #18: 用單一 Promise 而非 callback 佇列，避免並發 401 時
// 因 push/iterate 非原子操作而漏掉某些等待者。
// refreshPromise 為 null 代表沒有刷新中；非 null 即所有並發請求應 await 同一個。
let refreshPromise = null

// Drop any in-flight refresh attempt — called from auth.logout() so the next
// signed-in user does not inherit the previous user's pending refresh result.
export function resetRefreshState() {
  refreshPromise = null
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
        originalConfig._retry = true

        // Bug #18: 同時間僅啟動一個 refresh 請求；其餘並發 401 共享同個 Promise。
        // 使用 Promise 而非可變佇列，避免「先檢查 isRefreshing → 後 push」之間
        // 的非原子視窗造成 callback 漏注冊。
        if (!refreshPromise) {
          refreshPromise = (async () => {
            try {
              const res = await axios.post(
                `${api.defaults.baseURL}/api/auth/refresh`,
                { refresh_token: auth.refreshToken }
              )
              const { access_token, refresh_token, user_id, role, display_name } = res.data.data
              auth.setAuth(access_token, { user_id, role, display_name }, refresh_token)
              return access_token
            } finally {
              // 將 promise 清除延後到 microtask 之後，確保所有同步排隊的等待者
              // 都已掛上 .then 才釋放，避免後續請求重新觸發 refresh。
              setTimeout(() => { refreshPromise = null }, 0)
            }
          })()
        }

        try {
          const newToken = await refreshPromise
          originalConfig.headers.Authorization = `Bearer ${newToken}`
          return api.request(originalConfig)
        } catch (refreshError) {
          auth.logout()
          window.location.href = '/login'
          return Promise.reject(refreshError)
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
