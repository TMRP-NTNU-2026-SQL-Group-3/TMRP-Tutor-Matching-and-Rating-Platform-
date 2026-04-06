<template>
  <div class="min-h-[80vh] flex items-center justify-center">
    <div class="w-full max-w-md bg-white rounded-xl shadow-lg p-8">
      <div class="text-center mb-8">
        <h1 class="text-2xl font-bold text-primary-600">TMRP</h1>
        <p class="text-gray-500 mt-1">家教媒合與評價平台</p>
      </div>

      <form @submit.prevent="handleLogin" class="space-y-5">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">帳號</label>
          <input v-model="username" type="text" required
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">密碼</label>
          <input v-model="password" type="password" required
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
        </div>

        <p v-if="error" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ error }}</p>

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
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'

const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const error = ref('')
const submitting = ref(false)

async function handleLogin() {
  submitting.value = true
  try {
    error.value = ''
    const data = await authApi.login(username.value, password.value)
    auth.setAuth(data.access_token, {
      user_id: data.user_id,
      role: data.role,
      display_name: data.display_name
    }, data.refresh_token)
    if (data.role === 'admin') router.push('/admin')
    else if (data.role === 'tutor') router.push('/tutor')
    else router.push('/parent')
  } catch (e) {
    error.value = e.message
  } finally {
    submitting.value = false
  }
}
</script>
