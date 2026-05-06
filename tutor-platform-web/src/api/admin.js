import api from './index'

// Multipart upload helper. Axios derives the correct
// `multipart/form-data; boundary=...` header ONLY when Content-Type is
// absent from the request config — an interceptor that sets a default
// `application/json` would otherwise clobber it and make FastAPI fail to
// parse the body (the original Bug #27). Setting `Content-Type: undefined`
// tells axios to strip any inherited default and re-derive from the
// FormData body. Route every multipart POST through here so that rule
// lives in exactly one place.
function postMultipart(url, formData, config = {}) {
  return api.post(url, formData, {
    ...config,
    headers: { ...(config.headers || {}), 'Content-Type': undefined },
  })
}

export const adminApi = {
  listUsers() {
    return api.get('/api/admin/users')
  },
  seedData() {
    // FE-13: seed can generate thousands of rows; 30s default is too short.
    return api.post('/api/admin/seed', undefined, { timeout: 120000 })
  },
  importCsv(formData, tableName) {
    return postMultipart(
      `/api/admin/import?table_name=${encodeURIComponent(tableName)}`,
      formData,
      { timeout: 120000 },
    )
  },
  exportCsv(tableName) {
    return api.get(`/api/admin/export/${tableName}`, { responseType: 'blob', timeout: 120000 })
  },
  exportAll() {
    return api.post('/api/admin/export-all', null, { responseType: 'blob', timeout: 120000 })
  },
  // H-04: two-step reset. Caller is expected to prompt the admin for their
  // password between step 1 and step 2 — never cache or auto-fill it.
  requestReset() {
    return api.post('/api/admin/reset/request')
  },
  confirmReset(resetToken, password) {
    return api.post('/api/admin/reset/confirm', {
      reset_token: resetToken,
      password,
    })
  },
  getSystemStatus() {
    return api.get('/api/admin/system-status')
  },
  importAll(formData, clearFirst = false) {
    return postMultipart(`/api/admin/import-all?clear_first=${clearFirst}`, formData, { timeout: 120000 })
  },
}
