import api from './index'

export const authApi = {
  login(username, password) {
    return api.post('/api/auth/login', { username, password })
  },
  register(data) {
    return api.post('/api/auth/register', data)
  },
  getMe() {
    return api.get('/api/auth/me')
  }
}
