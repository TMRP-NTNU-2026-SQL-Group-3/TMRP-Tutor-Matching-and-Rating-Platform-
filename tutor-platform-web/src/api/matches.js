import api from './index'

export const matchesApi = {
  create(data) {
    return api.post('/api/matches', data)
  },
  list() {
    return api.get('/api/matches')
  },
  getDetail(matchId) {
    return api.get(`/api/matches/${matchId}`)
  },
  updateStatus(matchId, action, reason = null) {
    const body = { action }
    if (reason) body.reason = reason
    return api.patch(`/api/matches/${matchId}/status`, body)
  }
}
