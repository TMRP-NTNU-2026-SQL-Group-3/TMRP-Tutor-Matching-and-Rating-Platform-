import api from './index'

export const examsApi = {
  create(data) {
    return api.post('/api/exams', data)
  },
  list(params, config) {
    return api.get('/api/exams', { params, ...config })
  },
  update(examId, data) {
    return api.put(`/api/exams/${examId}`, data)
  }
}
