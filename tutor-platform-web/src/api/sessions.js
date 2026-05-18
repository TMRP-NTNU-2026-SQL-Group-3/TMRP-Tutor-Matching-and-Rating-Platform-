import api from './index'

export const sessionsApi = {
  create({ match_id, ...body }) {
    return api.post(`/api/matches/${match_id}/sessions`, body)
  },
  list({ match_id, ...params }, config) {
    return api.get(`/api/matches/${match_id}/sessions`, { params, ...config })
  },
  update(sessionId, data) {
    return api.put(`/api/sessions/${sessionId}`, data)
  },
  delete(sessionId) {
    return api.delete(`/api/sessions/${sessionId}`)
  },
  getEditLogs(sessionId) {
    return api.get(`/api/sessions/${sessionId}/edit-logs`)
  }
}
