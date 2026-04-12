import api from './index'

export const adminApi = {
  listUsers() {
    return api.get('/api/admin/users')
  },
  seedData() {
    return api.post('/api/admin/seed')
  },
  importCsv(formData, tableName) {
    // Bug #27: 顯式設 Content-Type 為 undefined 讓 axios 自動帶上正確的
    // multipart boundary；若被攔截器其他預設 header 覆蓋成 application/json
    // 會導致後端解析 FormData 失敗。
    return api.post(
      `/api/admin/import?table_name=${encodeURIComponent(tableName)}`,
      formData,
      { headers: { 'Content-Type': undefined } },
    )
  },
  exportCsv(tableName) {
    return api.get(`/api/admin/export/${tableName}`, { responseType: 'blob' })
  },
  exportAll() {
    return api.post('/api/admin/export-all', null, { responseType: 'blob' })
  },
  resetDatabase() {
    return api.post('/api/admin/reset?confirm=true')
  },
  getSystemStatus() {
    return api.get('/api/admin/system-status')
  },
  importAll(formData, clearFirst = false) {
    // Bug #27: 同 importCsv，明確讓 axios 自填 multipart boundary
    return api.post(
      `/api/admin/import-all?clear_first=${clearFirst}`,
      formData,
      { headers: { 'Content-Type': undefined } },
    )
  },
  getTaskStatus(taskId) {
    return api.get(`/api/admin/tasks/${taskId}`)
  },
}
