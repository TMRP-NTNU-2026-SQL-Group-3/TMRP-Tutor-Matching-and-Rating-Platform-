<template>
  <div id="app">
    <AppNav v-if="auth.isLoggedIn" :auth="auth" @logout="handleLogout" />

    <main class="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <router-view v-slot="{ Component }">
        <Transition name="fade" mode="out-in">
          <component :is="Component" />
        </Transition>
      </router-view>
    </main>

    <ToastNotification />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'
import AppNav from '@/components/common/AppNav.vue'
import ToastNotification from '@/components/common/ToastNotification.vue'

const router = useRouter()
const auth = useAuthStore()

// F3: 每次頁面載入時驗證已儲存的 token 是否仍有效
onMounted(async () => {
  if (auth.token) {
    try {
      const user = await authApi.getMe()
      auth.setAuth(auth.token, user)
    } catch {
      auth.logout()
      router.push('/login')
    }
  }
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
