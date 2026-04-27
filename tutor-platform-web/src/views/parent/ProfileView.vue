<template>
  <div>
    <PageHeader title="帳號設定" />

    <div v-if="loading" class="text-center py-8 text-gray-500">載入中...</div>

    <div v-else class="space-y-6">
      <!-- Account info -->
      <form @submit.prevent="handleSaveInfo" class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-4">
        <h2 class="text-lg font-semibold text-gray-900">基本資料</h2>

        <div>
          <label for="display-name" class="block text-sm font-medium text-gray-700 mb-1">顯示名稱</label>
          <input id="display-name" v-model="info.display_name" type="text" required maxlength="100"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
        </div>

        <div>
          <label for="phone" class="block text-sm font-medium text-gray-700 mb-1">聯絡電話</label>
          <input id="phone" v-model="info.phone" type="tel" maxlength="20" placeholder="選填"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
        </div>

        <div>
          <label for="email" class="block text-sm font-medium text-gray-700 mb-1">電子信箱</label>
          <input id="email" v-model="info.email" type="email" maxlength="100" placeholder="選填"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
        </div>

        <p v-if="infoError" role="alert" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ infoError }}</p>
        <p v-if="infoSuccess" role="status" class="text-sm text-green-700 bg-green-50 rounded-lg p-3">{{ infoSuccess }}</p>

        <button type="submit" :disabled="savingInfo"
          class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-6 py-2.5 text-sm font-medium transition-colors disabled:opacity-50">
          {{ savingInfo ? '儲存中...' : '儲存資料' }}
        </button>
      </form>

      <!-- Change password -->
      <form @submit.prevent="handleChangePassword" class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-4">
        <h2 class="text-lg font-semibold text-gray-900">變更密碼</h2>

        <div>
          <label for="current-password" class="block text-sm font-medium text-gray-700 mb-1">目前密碼</label>
          <input id="current-password" v-model="pw.current" type="password" required autocomplete="current-password"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
        </div>

        <div>
          <label for="new-password" class="block text-sm font-medium text-gray-700 mb-1">新密碼</label>
          <input id="new-password" v-model="pw.next" type="password" required autocomplete="new-password"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
          <p class="text-xs text-gray-400 mt-1">至少 10 個字元，須包含英文字母與數字</p>
        </div>

        <div>
          <label for="confirm-password" class="block text-sm font-medium text-gray-700 mb-1">確認新密碼</label>
          <input id="confirm-password" v-model="pw.confirm" type="password" required autocomplete="new-password"
            :aria-invalid="pwMismatch || null"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition"
            :class="pwMismatch ? 'border-red-400' : ''" />
          <p v-if="pwMismatch" class="text-xs text-red-500 mt-1">兩次輸入的密碼不一致</p>
        </div>

        <p v-if="pwError" role="alert" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ pwError }}</p>
        <p v-if="pwSuccess" role="status" class="text-sm text-green-700 bg-green-50 rounded-lg p-3">{{ pwSuccess }}</p>

        <button type="submit" :disabled="savingPw || pwMismatch || !pw.current || !pw.next || !pw.confirm"
          class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-6 py-2.5 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
          {{ savingPw ? '更新中...' : '更新密碼' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'
import PageHeader from '@/components/common/PageHeader.vue'

const auth = useAuthStore()

const loading = ref(false)
const savingInfo = ref(false)
const infoError = ref('')
const infoSuccess = ref('')
const savingPw = ref(false)
const pwError = ref('')
const pwSuccess = ref('')

const info = reactive({ display_name: '', phone: '', email: '' })
const pw = reactive({ current: '', next: '', confirm: '' })

const pwMismatch = computed(() => pw.confirm.length > 0 && pw.next !== pw.confirm)

let infoTimer = null
let pwTimer = null
let isMounted = true

onUnmounted(() => {
  isMounted = false
  if (infoTimer) clearTimeout(infoTimer)
  if (pwTimer) clearTimeout(pwTimer)
})

async function handleSaveInfo() {
  if (savingInfo.value) return
  infoError.value = ''
  infoSuccess.value = ''
  savingInfo.value = true
  try {
    const updated = await authApi.updateMe({
      display_name: info.display_name,
      phone: info.phone || null,
      email: info.email || null,
    })
    if (!isMounted) return
    info.display_name = updated.display_name || ''
    info.phone = updated.phone || ''
    info.email = updated.email || ''
    // Keep the nav display name in sync without re-triggering login-flow side effects.
    auth.updateUser({ display_name: updated.display_name })
    infoSuccess.value = '資料已更新'
    if (infoTimer) clearTimeout(infoTimer)
    infoTimer = setTimeout(() => { infoSuccess.value = ''; infoTimer = null }, 3000)
  } catch (e) {
    if (isMounted) infoError.value = e.message
  } finally {
    if (isMounted) savingInfo.value = false
  }
}

async function handleChangePassword() {
  if (savingPw.value || pwMismatch.value) return
  pwError.value = ''
  pwSuccess.value = ''
  savingPw.value = true
  try {
    await authApi.changePassword({ current_password: pw.current, new_password: pw.next })
    if (!isMounted) return
    pw.current = ''
    pw.next = ''
    pw.confirm = ''
    pwSuccess.value = '密碼已更新'
    if (pwTimer) clearTimeout(pwTimer)
    pwTimer = setTimeout(() => { pwSuccess.value = ''; pwTimer = null }, 3000)
  } catch (e) {
    if (isMounted) pwError.value = e.message
  } finally {
    if (isMounted) savingPw.value = false
  }
}

onMounted(async () => {
  loading.value = true
  try {
    const user = await authApi.getMe()
    if (!isMounted) return
    info.display_name = user.display_name || ''
    info.phone = user.phone || ''
    info.email = user.email || ''
  } catch (e) {
    if (isMounted) infoError.value = e.message
  } finally {
    loading.value = false
  }
})
</script>
