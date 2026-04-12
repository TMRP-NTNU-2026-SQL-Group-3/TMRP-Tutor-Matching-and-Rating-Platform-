// Bridge between the HTTP transport (api/index.js) and the auth store /
// router. Keeping this in its own module means the transport layer has no
// runtime dependency on Pinia or the DOM, which is what made the old
// interceptor painful to test and rigid to change.

import { useAuthStore } from '@/stores/auth'

export function getAccessToken() {
  return useAuthStore().token || ''
}

export function getRefreshToken() {
  return useAuthStore().refreshToken || ''
}

export function applyRefreshedAuth({ access_token, refresh_token, user_id, role, display_name }) {
  useAuthStore().setAuth(access_token, { user_id, role, display_name }, refresh_token)
}

export function handleAuthLost() {
  useAuthStore().logout()
  if (typeof window !== 'undefined') {
    window.location.href = '/login'
  }
}
