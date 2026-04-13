import axios from 'axios'
import { API_BASE_URL } from './baseURL'
import {
  applyRefreshedAuth,
  getAccessToken,
  getRefreshToken,
  handleAuthLost,
} from './authHandler'

// Re-export so callers can keep doing `import { API_BASE_URL } from '@/api'`.
export { API_BASE_URL }

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
})

// P-BIZ-02 / Bug #18: single in-flight refresh, shared via one Promise rather
// than a mutable callback queue — avoids the non-atomic push/iterate window
// that could drop waiters under concurrent 401s.
let refreshPromise = null

// F-06: fence raised by logout() so a 401 from any request still in flight at
// logout time cannot kick off a fresh refresh (which would resurrect tokens
// the user just discarded). Cleared by markLoggedIn() at the next setAuth().
let loggingOut = false

// Called from auth.logout() so a stale refresh from the previous session
// cannot resolve into the next user's request stream, and to raise the
// loggingOut fence (F-06) until the next successful login.
export function resetRefreshState() {
  refreshPromise = null
  loggingOut = true
}

// Called from auth.setAuth() once a new session is established — drops the
// loggingOut fence so normal refresh-on-401 resumes for the new user.
export function markLoggedIn() {
  loggingOut = false
}

// ── Transport: attach bearer token ──────────────────────────────
api.interceptors.request.use(config => {
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ── Transport: response unwrap + refresh + retry ────────────────
async function refreshAccessToken() {
  // F-06: refuse to start a new refresh while logout is fencing — any 401
  // arriving in this window must fall through to handleAuthLost rather than
  // re-establishing the session the user just left.
  if (loggingOut) {
    throw new Error('logged out')
  }
  if (!refreshPromise) {
    refreshPromise = (async () => {
      try {
        const res = await axios.post(
          `${api.defaults.baseURL}/api/auth/refresh`,
          { refresh_token: getRefreshToken() }
        )
        applyRefreshedAuth(res.data.data)
        return res.data.data.access_token
      } finally {
        // Release after the current microtask so all synchronous waiters
        // have already attached their `.then` before the next request
        // decides whether to start a fresh refresh cycle.
        setTimeout(() => { refreshPromise = null }, 0)
      }
    })()
  }
  return refreshPromise
}

// F-15: envelope unwrap only applies to JSON responses. Blob downloads
// (CSV export) and upstream HTML error pages must pass through untouched,
// so check Content-Type before attempting to read {success,data,message}.
function isJsonResponse(response) {
  const ctype = response?.headers?.['content-type']
  if (typeof ctype === 'string') {
    return ctype.toLowerCase().includes('application/json')
  }
  // Fall back to shape-based detection when the header is absent.
  const body = response?.data
  return body != null && typeof body === 'object' && !(body instanceof Blob) && 'success' in body
}

api.interceptors.response.use(
  response => {
    if (!isJsonResponse(response)) {
      return response.data
    }
    const body = response.data
    if (body == null || typeof body !== 'object' || !('success' in body)) {
      return body
    }
    const { success, data, message } = body
    if (!success) {
      return Promise.reject(new Error(message || '操作失敗'))
    }
    return data
  },
  async error => {
    // F-07: caller-initiated cancellation (AbortController.abort()) must not
    // trigger refresh-on-401 or 5xx retry — there's no caller waiting for the
    // result anymore. Re-throw as-is so callers can detect via axios.isCancel.
    if (axios.isCancel(error) || error.name === 'CanceledError' || error.name === 'AbortError') {
      return Promise.reject(error)
    }

    const originalConfig = error.config

    // 401 — attempt refresh, retry once.
    if (error.response?.status === 401 && !originalConfig._retry) {
      if (getRefreshToken()) {
        originalConfig._retry = true
        try {
          const newToken = await refreshAccessToken()
          originalConfig.headers.Authorization = `Bearer ${newToken}`
          return api.request(originalConfig)
        } catch (refreshError) {
          handleAuthLost()
          return Promise.reject(refreshError)
        }
      }
      handleAuthLost()
      return Promise.reject(error)
    }

    // 5xx / network — exponential backoff, up to 2 retries.
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
