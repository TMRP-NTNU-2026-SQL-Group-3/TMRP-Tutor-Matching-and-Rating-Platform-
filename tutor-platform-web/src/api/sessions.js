import api from './index'

export const sessionsApi = {
  create(data) {
    return api.post('/api/sessions', data)
  },
  list(params) {
    return api.get('/api/sessions', { params })
  },
  update(sessionId, data) {
    return api.put(`/api/sessions/${sessionId}`, data)
  },
  getEditLogs(sessionId) {
    return api.get(`/api/sessions/${sessionId}/edit-logs`)
  }
}
