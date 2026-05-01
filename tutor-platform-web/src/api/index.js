import axios from 'axios'
import { API_BASE_URL } from './baseURL'
import {
  applyRefreshedAuth,
  handleAuthLost,
} from './authHandler'

// Re-export so callers can keep doing `import { API_BASE_URL } from '@/api'`.
export { API_BASE_URL }

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  // SEC-C02: send HttpOnly cookies on every request.
  withCredentials: true,
})

// P-BIZ-02 / Bug #18: single in-flight refresh, shared via one Promise rather
// than a mutable callback queue — avoids the non-atomic push/iterate window
// that could drop waiters under concurrent 401s.
let refreshPromise = null

// F-06: fence raised by logout() so a 401 from any request still in flight at
// logout time cannot kick off a fresh refresh (which would resurrect tokens
// the user just discarded). Cleared by markLoggedIn() at the next setAuth().
let loggingOut = false

// SEC-H03: shared AbortController — every outgoing request gets its signal so
// logout() can cancel all in-flight requests, preventing a late 401 response
// from triggering a token refresh that would resurrect the old session.
let inflightController = new AbortController()

// Called from auth.logout() so a stale refresh from the previous session
// cannot resolve into the next user's request stream, and to raise the
// loggingOut fence (F-06) until the next successful login.
export function resetRefreshState() {
  refreshPromise = null
  loggingOut = true
  // Abort every request still in flight from the previous session.
  inflightController.abort()
  inflightController = new AbortController()
}

// Called from auth.setAuth() once a new session is established — drops the
// loggingOut fence so normal refresh-on-401 resumes for the new user.
export function markLoggedIn() {
  loggingOut = false
}

// ── Transport: attach abort signal + CSRF token ─────────────────
// SEC-C02: Authorization header is no longer needed — HttpOnly cookies are
// sent automatically by the browser via withCredentials.
// HIGH-3 / SEC-03: dual CSRF defense.
//   1. X-Requested-With forces a CORS preflight on cross-origin requests so
//      a non-whitelisted origin is rejected before the route handler runs.
//   2. X-CSRF-Token implements the double-submit cookie pattern: the server
//      sets a non-httpOnly `csrf_token` cookie on login; the SPA reads it via
//      getCsrfToken() and reflects it here. CSRFMiddleware validates that the
//      cookie and header values match, blocking any origin that cannot read
//      the cookie (i.e. every origin that is not the SPA's own origin).
const CSRF_METHODS = new Set(['post', 'put', 'patch', 'delete'])

// FE-4: guard decodeURIComponent and handle cookie values that contain '='.
function getCsrfToken() {
  const entry = document.cookie.split('; ').find(c => c.startsWith('csrf_token='))
  if (!entry) return ''
  try {
    return decodeURIComponent(entry.slice('csrf_token='.length))
  } catch {
    return ''
  }
}

api.interceptors.request.use(config => {
  // SEC-H03: attach the shared abort signal so logout() can cancel all
  // pending requests. Callers that supply their own signal are unaffected.
  if (!config.signal) {
    config.signal = inflightController.signal
  }
  const method = (config.method || 'get').toLowerCase()
  if (CSRF_METHODS.has(method)) {
    config.headers = config.headers || {}
    config.headers['X-Requested-With'] = 'XMLHttpRequest'
    const token = getCsrfToken()
    if (token) {
      config.headers['X-CSRF-Token'] = token
    } else if (process.env.NODE_ENV !== 'production') {
      // Expected before login; a warning here surfaces misconfigured cookie
      // domains or missing Set-Cookie headers early in development.
      console.warn('[CSRF] X-CSRF-Token absent for', method.toUpperCase(), config.url)
    }
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
        // SEC-C02: refresh_token is sent automatically via HttpOnly cookie.
        // The server sets fresh cookies in the response; we only need the
        // user-info payload to keep the store in sync.
        const _csrfToken = getCsrfToken()
        const res = await axios.post(
          `${api.defaults.baseURL}/api/auth/refresh`,
          null,
          {
            withCredentials: true,
            // HIGH-3 / SEC-03: this call bypasses the `api` instance interceptor,
            // so attach both CSRF headers directly.
            headers: {
              'X-Requested-With': 'XMLHttpRequest',
              ...(_csrfToken && { 'X-CSRF-Token': _csrfToken }),
            },
          },
        )
        // FE-8: re-check loggingOut after the await — the response may have
        // arrived in the network buffer just before abort() was called, so the
        // top-of-function guard does not cover this window.
        if (!loggingOut) {
          applyRefreshedAuth(res.data.data)
        }
      } finally {
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
      // FE-12: log raw backend message in dev before it may be exposed to users.
      if (process.env.NODE_ENV !== 'production') {
        console.error('[API] business error:', message, body)
      }
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
    // SEC-C02: refresh_token is in an HttpOnly cookie (not readable by JS).
    // Always attempt refresh on 401; if the cookie is absent/expired the
    // server will reject and we fall through to handleAuthLost().
    if (error.response?.status === 401 && !originalConfig._retry) {
      originalConfig._retry = true
      try {
        await refreshAccessToken()
        // Retry with fresh cookies (set by the refresh response).
        return api.request(originalConfig)
      } catch (refreshError) {
        handleAuthLost()
        return Promise.reject(refreshError)
      }
    }

    // 5xx / network — exponential backoff, up to 2 retries.
    const retryCount = originalConfig._retryCount || 0
    const isRetryable = !error.response || error.response.status >= 500 || error.code === 'ECONNABORTED'
    if (isRetryable && retryCount < 2) {
      originalConfig._retryCount = retryCount + 1
      await new Promise((r) => setTimeout(r, 1000 * 2 ** retryCount))
      return api.request(originalConfig)
    }

    // FE-12: extract raw message for logging, then sanitize for the user.
    // 5xx responses may contain internal details (DB field names, stack traces);
    // replace them with a generic string. 4xx messages are intentional for users.
    let rawMessage = '網路連線異常'
    if (error.response?.data instanceof Blob) {
      try {
        const text = await error.response.data.text()
        const json = JSON.parse(text)
        rawMessage = json.message || rawMessage
      } catch { /* ignore parse errors */ }
    } else {
      rawMessage = error.response?.data?.message || rawMessage
    }
    if (process.env.NODE_ENV !== 'production') {
      console.error('[API] request error:', rawMessage, error.response?.status, error.config?.url)
    }
    const status = error.response?.status
    const message = (status && status >= 500) ? '伺服器發生錯誤，請稍後再試' : rawMessage
    return Promise.reject(new Error(message))
  }
)

export default api
