<template>
  <div class="min-h-[80vh] flex items-center justify-center">
    <div class="w-full max-w-md bg-white rounded-xl shadow-lg p-8">
      <div class="text-center mb-8">
        <h1 class="text-2xl font-bold text-primary-600">TMRP</h1>
        <p class="text-gray-500 mt-1">家教媒合與評價平台</p>
      </div>

      <form @submit.prevent="handleLogin" class="space-y-5">
        <div>
          <label for="login-username" class="block text-sm font-medium text-gray-700 mb-1">帳號</label>
          <input id="login-username" v-model="username" type="text" required autocomplete="username"
            :aria-invalid="!!error || null" aria-describedby="login-error"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
        </div>
        <div>
          <label for="login-password" class="block text-sm font-medium text-gray-700 mb-1">密碼</label>
          <div class="relative">
            <input id="login-password" v-model="password" :type="showPassword ? 'text' : 'password'" required
              autocomplete="current-password"
              :aria-invalid="!!error || null" aria-describedby="login-error"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 pr-16 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
            <button type="button" @click="showPassword = !showPassword"
              :aria-label="showPassword ? '隱藏密碼' : '顯示密碼'"
              class="absolute inset-y-0 right-0 flex items-center px-3 text-xs text-gray-500 hover:text-primary-600 transition-colors">
              {{ showPassword ? '隱藏' : '顯示' }}
            </button>
          </div>
        </div>

        <label class="flex items-center gap-2 text-sm text-gray-600 cursor-pointer select-none">
          <input v-model="rememberMe" type="checkbox"
            class="rounded border-gray-300 text-primary-600 focus:ring-primary-500" />
          記住我
        </label>

        <p v-if="error" id="login-error" role="alert" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ error }}</p>

        <button type="submit" :disabled="submitting || !username || !password"
          class="w-full bg-primary-600 hover:bg-primary-700 text-white rounded-lg py-2.5 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
          登入
        </button>
      </form>

      <p class="text-center text-sm text-gray-500 mt-6">
        還沒有帳號？
        <router-link to="/register" class="text-primary-600 font-medium hover:underline">註冊</router-link>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const REMEMBERED_USERNAME_KEY = 'login:rememberedUsername'
const username = ref(localStorage.getItem(REMEMBERED_USERNAME_KEY) || '')
const password = ref('')
const rememberMe = ref(!!localStorage.getItem(REMEMBERED_USERNAME_KEY))
const showPassword = ref(false)
const error = ref('')
const submitting = ref(false)

async function handleLogin() {
  submitting.value = true
  try {
    error.value = ''
    const data = await authApi.login(username.value, password.value)
    if (rememberMe.value) {
      localStorage.setItem(REMEMBERED_USERNAME_KEY, username.value)
    } else {
      localStorage.removeItem(REMEMBERED_USERNAME_KEY)
    }
    // SEC-C02: tokens are delivered via HttpOnly cookies by the server;
    // we only store non-sensitive user info in the frontend.
    auth.setAuth({
      user_id: data.user_id,
      role: data.role,
      display_name: data.display_name
    })
    // P-BIZ-03: 使用對照表處理角色路由，未知角色顯示錯誤
    const roleRoutes = { admin: '/admin', tutor: '/tutor', parent: '/parent' }
    const target = roleRoutes[data.role]
    if (target) {
      // F-FEAT-05: honour the ?redirect= param set by the router guard so
      // deep links and bookmarked protected pages work after login.
      const redirect = route.query.redirect
      const dest = (redirect && typeof redirect === 'string' && redirect.startsWith('/') && !redirect.startsWith('//'))
        ? redirect
        : target
      router.push(dest)
    } else {
      error.value = `不支援的帳號角色：${data.role}`
      auth.logout()
    }
  } catch (e) {
    error.value = e.message
  } finally {
    submitting.value = false
  }
}
</script>
