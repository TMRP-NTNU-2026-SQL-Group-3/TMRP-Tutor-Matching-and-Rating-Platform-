import api from './index'

export const reviewsApi = {
  create(data) {
    return api.post('/api/reviews', data)
  },
  list(params, config) {
    return api.get('/api/reviews', { params, ...config })
  },
  update(reviewId, data) {
    return api.patch(`/api/reviews/${reviewId}`, data)
  }
}
