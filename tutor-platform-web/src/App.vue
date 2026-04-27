<template>
  <div id="app">
    <AppNav v-if="auth.isLoggedIn" :auth="auth" @logout="handleLogout" />

    <main class="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <template v-if="!validating">
        <router-view v-slot="{ Component }">
          <Transition name="fade" mode="out-in">
            <component :is="Component" />
          </Transition>
        </router-view>
      </template>
    </main>

    <ToastNotification />
    <ConfirmDialog />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { useNotificationStore } from '@/stores/notifications'
import { authApi } from '@/api/auth'
import AppNav from '@/components/common/AppNav.vue'
import ToastNotification from '@/components/common/ToastNotification.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'

const router = useRouter()
const auth = useAuthStore()

// Wire toast events to the notification history at the app root so the two
// stores remain independent. $onAction fires before each action executes and
// returns an unsubscribe handle — no cleanup needed for a root component.
const _TOAST_TYPES = new Set(['success', 'error', 'warning', 'info'])
useToastStore().$onAction(({ name, args }) => {
  if (_TOAST_TYPES.has(name)) useNotificationStore().add(name, args[0])
})

// F3: on every page load, verify the session is still valid by calling /me.
// SEC-C02: the HttpOnly cookie is sent automatically — we only check whether
// localStorage still has user info (indicating a prior session).
const validating = ref(true)
onMounted(async () => {
  if (auth.isLoggedIn) {
    try {
      const user = await authApi.getMe()
      auth.setAuth(user)
    } catch {
      auth.logout()
      router.push('/login')
    }
  }
  validating.value = false
})

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
