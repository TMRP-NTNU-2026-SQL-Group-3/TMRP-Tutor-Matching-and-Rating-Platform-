import api from './index'

export const adminApi = {
  listUsers() {
    return api.get('/api/admin/users')
  },
  seedData() {
    return api.post('/api/admin/seed')
  },
  importCsv(formData, tableName) {
    return api.post(`/api/admin/import?table_name=${encodeURIComponent(tableName)}`, formData)
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
    return api.post(`/api/admin/import-all?clear_first=${clearFirst}`, formData)
  },
  getTaskStatus(taskId) {
    return api.get(`/api/admin/tasks/${taskId}`)
  },
}
