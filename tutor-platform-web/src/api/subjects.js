import api from './index'

export const subjectsApi = {
  list() {
    return api.get('/api/subjects')
  }
}
