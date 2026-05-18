import api from './index'

export const examsApi = {
  create({ student_id, ...body }) {
    return api.post(`/api/students/${student_id}/exams`, body)
  },
  list({ student_id, ...params }, config) {
    return api.get(`/api/students/${student_id}/exams`, { params, ...config })
  },
  update(examId, data) {
    return api.put(`/api/exams/${examId}`, data)
  },
  delete(examId) {
    return api.delete(`/api/exams/${examId}`)
  }
}
