// Bridge between the HTTP transport (api/index.js) and the auth store /
// router. Keeping this in its own module means the transport layer has no
// runtime dependency on Pinia or the DOM, which is what made the old
// interceptor painful to test and rigid to change.
//
// SEC-C02: tokens are now in HttpOnly cookies — JS never reads or writes
// them. This module only syncs *user info* between the transport and the
// auth store.

import { useAuthStore } from '@/stores/auth'

export function applyRefreshedAuth({ user_id, role, display_name }) {
  useAuthStore().setAuth({ user_id, role, display_name })
}

export function handleAuthLost() {
  useAuthStore().logout()
  if (typeof window !== 'undefined') {
    window.location.href = '/login'
  }
}
