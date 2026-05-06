import api from './index'

export const tutorsApi = {
  search(params) {
    return api.get('/api/tutors', { params })
  },
  getDetail(tutorId) {
    return api.get(`/api/tutors/${tutorId}`)
  },
  getMyProfile() {
    return api.get('/api/tutors/me')
  },
  updateProfile(data) {
    return api.put('/api/tutors/profile', data)
  },
  updateSubjects(data) {
    return api.put('/api/tutors/profile/subjects', data)
  },
  updateAvailability(data) {
    return api.put('/api/tutors/profile/availability', data)
  },
  updateVisibility(data) {
    return api.put('/api/tutors/profile/visibility', data)
  },
}
