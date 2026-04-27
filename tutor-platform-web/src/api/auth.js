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
  },
  updateMe(data) {
    return api.put('/api/auth/me', data)
  },
  changePassword(data) {
    return api.put('/api/auth/password', data)
  },
  // SEC-C02: refresh_token is sent via HttpOnly cookie automatically.
  logout() {
    return api.post('/api/auth/logout')
  }
}
