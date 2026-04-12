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
          <input v-model="form.password" type="password" required minlength="8"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
          <p class="text-xs mt-1" :class="passwordHintClass">至少 8 個字元，且需同時包含英文字母與數字</p>
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

        <p v-if="error" role="alert" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ error }}</p>

        <button type="submit" :disabled="submitting"
          class="w-full bg-primary-600 hover:bg-primary-700 text-white rounded-lg py-2.5 text-sm font-medium transition-colors disabled:opacity-50">
          {{ submitting ? '註冊中...' : '註冊' }}
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
import { ref, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import { authApi } from '@/api/auth'
import { useToastStore } from '@/stores/toast'

const router = useRouter()
const toast = useToastStore()
const error = ref('')
const submitting = ref(false)

const form = reactive({
  role: 'parent',
  username: '',
  password: '',
  display_name: '',
  phone: '',
  email: ''
})

const passwordValid = computed(() => {
  const v = form.password || ''
  return v.length >= 8 && /[A-Za-z]/.test(v) && /\d/.test(v)
})
const passwordHintClass = computed(() => {
  if (!form.password) return 'text-gray-500'
  return passwordValid.value ? 'text-green-600' : 'text-red-500'
})

async function handleRegister() {
  if (submitting.value) return
  // P-BIZ-04: 前端驗證角色合法性
  if (!['parent', 'tutor'].includes(form.role)) {
    error.value = '不合法的角色'
    return
  }
  if (!passwordValid.value) {
    error.value = '密碼至少 8 個字元，且需同時包含英文字母與數字'
    return
  }
  submitting.value = true
  try {
    error.value = ''
    const payload = {
      ...form,
      phone: form.phone?.trim() || null,
      email: form.email?.trim() || null,
    }
    await authApi.register(payload)
    toast.success('註冊成功！請以新帳號登入')
    router.push('/login')
  } catch (e) {
    error.value = e.message
  } finally {
    submitting.value = false
  }
}
</script>
