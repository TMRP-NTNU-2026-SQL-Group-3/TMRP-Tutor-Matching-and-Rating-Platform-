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
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'
import AppNav from '@/components/common/AppNav.vue'
import ToastNotification from '@/components/common/ToastNotification.vue'

const router = useRouter()
const auth = useAuthStore()

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
