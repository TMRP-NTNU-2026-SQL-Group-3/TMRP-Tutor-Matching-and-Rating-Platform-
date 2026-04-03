import api from './index'

export const statsApi = {
  getIncome(params) {
    return api.get('/api/stats/income', { params })
  },
  getExpense(params) {
    return api.get('/api/stats/expense', { params })
  },
  getStudentProgress(studentId, params) {
    return api.get(`/api/stats/student-progress/${studentId}`, { params })
  }
}
