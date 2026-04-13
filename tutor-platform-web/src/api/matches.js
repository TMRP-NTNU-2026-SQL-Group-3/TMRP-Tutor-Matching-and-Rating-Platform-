import api from './index'

export const matchesApi = {
  create(data) {
    return api.post('/api/matches', data)
  },
  list() {
    return api.get('/api/matches')
  },
  getDetail(matchId, config) {
    return api.get(`/api/matches/${matchId}`, config)
  },
  updateStatus(matchId, action, reason = null) {
    const body = { action }
    if (reason != null) body.reason = reason
    return api.patch(`/api/matches/${matchId}/status`, body)
  },
  // Spec Module D: trial → active confirmation may carry edited contract terms.
  confirmTrial(matchId, terms = {}) {
    const body = { action: 'confirm_trial' }
    if (terms.hourly_rate != null) body.hourly_rate = terms.hourly_rate
    if (terms.sessions_per_week != null) body.sessions_per_week = terms.sessions_per_week
    if (terms.start_date) body.start_date = terms.start_date
    return api.patch(`/api/matches/${matchId}/status`, body)
  }
}
