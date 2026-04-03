import api from './index'

export const studentsApi = {
  list() {
    return api.get('/api/students')
  },
  add(data) {
    return api.post('/api/students', data)
  },
  update(studentId, data) {
    return api.put(`/api/students/${studentId}`, data)
  }
}
