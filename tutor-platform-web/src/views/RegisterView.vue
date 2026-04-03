<template>
  <div class="min-h-[80vh] flex items-center justify-center">
    <div class="w-full max-w-md bg-white rounded-xl shadow-lg p-8">
      <div class="text-center mb-8">
        <h1 class="text-2xl font-bold text-primary-600">TMRP</h1>
        <p class="text-gray-500 mt-1">建立新帳號</p>
      </div>

      <form @submit.prevent="handleRegister" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">身份</label>
          <select v-model="form.role"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition">
            <option value="parent">家長</option>
            <option value="tutor">家教老師</option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">帳號</label>
          <input v-model="form.username" type="text" required
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">密碼</label>
          <input v-model="form.password" type="password" required
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">姓名</label>
          <input v-model="form.display_name" type="text" required
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">電話</label>
          <input v-model="form.phone" type="text"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Email</label>
          <input v-model="form.email" type="email"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
        </div>

        <p v-if="error" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ error }}</p>

        <button type="submit"
          class="w-full bg-primary-600 hover:bg-primary-700 text-white rounded-lg py-2.5 text-sm font-medium transition-colors">
          註冊
        </button>
      </form>

      <p class="text-center text-sm text-gray-500 mt-6">
        已有帳號？
        <router-link to="/login" class="text-primary-600 font-medium hover:underline">登入</router-link>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { authApi } from '@/api/auth'

const router = useRouter()
const error = ref('')

const form = reactive({
  role: 'parent',
  username: '',
  password: '',
  display_name: '',
  phone: '',
  email: ''
})

async function handleRegister() {
  try {
    error.value = ''
    await authApi.register(form)
    router.push('/login')
  } catch (e) {
    error.value = e.message
  }
}
</script>
