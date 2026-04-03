import api from './index'

export const examsApi = {
  create(data) {
    return api.post('/api/exams', data)
  },
  list(params) {
    return api.get('/api/exams', { params })
  },
  update(examId, data) {
    return api.put(`/api/exams/${examId}`, data)
  }
}
