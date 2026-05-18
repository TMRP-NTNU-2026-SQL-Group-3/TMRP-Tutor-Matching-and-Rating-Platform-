import api from './index'

export const reviewsApi = {
  create({ match_id, ...body }) {
    return api.post(`/api/matches/${match_id}/reviews`, body)
  },
  list({ match_id, ...params }, config) {
    return api.get(`/api/matches/${match_id}/reviews`, { params, ...config })
  },
  update(reviewId, data) {
    return api.patch(`/api/reviews/${reviewId}`, data)
  }
}
