import api from './index'

export const reviewsApi = {
  create(data) {
    return api.post('/api/reviews', data)
  },
  list(params) {
    return api.get('/api/reviews', { params })
  },
  update(reviewId, data) {
    return api.patch(`/api/reviews/${reviewId}`, data)
  }
}
