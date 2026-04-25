<template>
  <div>
    <PageHeader title="管理後台" />

    <!-- System status -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-gray-900">系統狀態</h2>
        <button @click="fetchSystemStatus" :disabled="loadingStatus"
          class="bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50">
          {{ loadingStatus ? '載入中...' : '重新載入' }}
        </button>
      </div>
      <div v-if="loadingStatus && !systemStatus" class="py-4 text-center text-sm text-gray-400">載入中...</div>
      <div v-else-if="systemStatus">
        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 mb-4">
          <button v-for="t in tables" :key="t" @click="drillTable(t)"
            :title="`匯出 ${t} CSV`"
            class="bg-gray-50 rounded-lg p-3 border border-gray-100 text-left hover:bg-primary-50 hover:border-primary-200 transition-colors cursor-pointer group">
            <div class="text-xs text-gray-500 truncate group-hover:text-primary-600" :title="t">{{ t }}</div>
            <div class="text-lg font-semibold text-gray-900 mt-0.5 group-hover:text-primary-700">
              {{ (systemStatus.table_counts?.[t] ?? 0).toLocaleString() }}
            </div>
            <div class="text-xs text-gray-400 mt-1 group-hover:text-primary-500">
              點擊匯出 CSV
            </div>
          </button>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <h3 class="text-sm font-semibold text-gray-700 mb-2">使用者角色</h3>
            <ul class="text-sm text-gray-600 space-y-1">
              <li v-for="(cnt, role) in systemStatus.role_counts" :key="role" class="flex justify-between">
                <span>{{ role }}</span><span class="font-medium text-gray-900">{{ cnt }}</span>
              </li>
              <li v-if="!Object.keys(systemStatus.role_counts || {}).length" class="text-gray-400">無資料</li>
            </ul>
          </div>
          <div>
            <h3 class="text-sm font-semibold text-gray-700 mb-2">配對狀態</h3>
            <ul class="text-sm text-gray-600 space-y-1">
              <li v-for="(cnt, status) in systemStatus.match_statuses" :key="status" class="flex justify-between">
                <span>{{ status }}</span><span class="font-medium text-gray-900">{{ cnt }}</span>
              </li>
              <li v-if="!Object.keys(systemStatus.match_statuses || {}).length" class="text-gray-400">無資料</li>
            </ul>
          </div>
        </div>
      </div>
      <p v-else class="text-sm text-gray-400">尚未載入</p>
    </div>

    <!-- Seed / reset data -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-6">
      <h2 class="text-lg font-semibold text-gray-900 mb-3">資料維護</h2>
      <div class="flex flex-wrap gap-3">
        <button @click="handleSeed" :disabled="seeding"
          class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
          {{ seeding ? '生成中...' : '生成假資料' }}
        </button>
        <button @click="handleReset" :disabled="resetting"
          class="bg-red-600 hover:bg-red-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
          {{ resetting ? '清空中...' : '清空資料庫' }}
        </button>
      </div>
      <p v-if="seedResult" class="text-sm text-green-700 bg-green-50 rounded-lg p-3 mt-3">{{ seedResult }}</p>
      <p v-if="resetResult" class="text-sm text-green-700 bg-green-50 rounded-lg p-3 mt-3">{{ resetResult }}</p>
    </div>

    <!-- Users -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-gray-900">使用者管理</h2>
        <button @click="fetchUsers" :disabled="loadingUsers"
          class="bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50">
          {{ loadingUsers ? '載入中...' : '重新載入' }}
        </button>
      </div>
      <div v-if="loadingUsers && !users.length" class="py-8 text-center text-sm text-gray-400">載入中...</div>
      <div v-else-if="users.length" class="overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="border-b border-gray-200">
              <th class="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">ID</th>
              <th class="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">帳號</th>
              <th class="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">顯示名稱</th>
              <th class="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">角色</th>
              <th class="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Email</th>
              <th class="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">電話</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <tr v-for="u in users" :key="u.user_id" class="hover:bg-gray-50 transition-colors">
              <td class="px-3 py-2.5 text-sm text-gray-500">{{ u.user_id }}</td>
              <td class="px-3 py-2.5 text-sm text-gray-900 font-medium">{{ u.username }}</td>
              <td class="px-3 py-2.5 text-sm text-gray-700">{{ u.display_name }}</td>
              <td class="px-3 py-2.5">
                <span :class="[
                  'px-2 py-0.5 rounded-full text-xs font-medium',
                  u.role === 'admin' ? 'bg-purple-100 text-purple-700' :
                  u.role === 'tutor' ? 'bg-blue-100 text-blue-700' :
                  'bg-green-100 text-green-700'
                ]">
                  {{ u.role }}
                </span>
              </td>
              <td class="px-3 py-2.5 text-sm text-gray-500">{{ u.email || '-' }}</td>
              <td class="px-3 py-2.5 text-sm text-gray-500">{{ u.phone || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else-if="!loadingUsers" class="text-gray-400 text-sm">尚無使用者資料</p>
    </div>

    <!-- CSV Export / Import -->
    <div class="grid md:grid-cols-2 gap-6 mb-6">
      <!-- Export -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-3">CSV 匯出</h2>
        <div class="flex gap-2 items-center">
          <select v-model="exportTable"
            class="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition">
            <option v-for="t in tables" :key="t" :value="t">{{ t }}</option>
          </select>
          <button @click="handleExport" :disabled="exporting"
            class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 shrink-0">
            {{ exporting ? '匯出中...' : '下載 CSV' }}
          </button>
        </div>
        <button @click="handleExportAll" :disabled="exportingAll"
          class="mt-3 w-full bg-green-600 hover:bg-green-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
          {{ exportingAll ? '匯出中...' : '一鍵匯出全部資料表 (ZIP)' }}
        </button>
      </div>

      <!-- Import -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-3">CSV 匯入</h2>
        <div class="space-y-3">
          <div class="flex gap-2 items-center">
            <select v-model="importTable"
              class="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition">
              <option v-for="t in tables" :key="t" :value="t">{{ t }}</option>
            </select>
          </div>
          <div class="flex gap-2 items-center">
            <input type="file" accept=".csv" ref="fileInput"
              class="flex-1 text-sm text-gray-500 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100" />
            <button @click="handleImport" :disabled="importing"
              class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 shrink-0">
              {{ importing ? '匯入中...' : '匯入' }}
            </button>
          </div>
          <p v-if="importResult" class="text-sm text-green-700 bg-green-50 rounded-lg p-3">{{ importResult }}</p>
          <hr class="border-gray-200" />
          <div class="flex gap-2 items-center">
            <input type="file" accept=".zip" ref="zipFileInput"
              class="flex-1 text-sm text-gray-500 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100" />
            <button @click="handleImportAll" :disabled="importingAll"
              class="bg-green-600 hover:bg-green-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 shrink-0">
              {{ importingAll ? '匯入中...' : '匯入全部 (ZIP)' }}
            </button>
          </div>
          <div class="flex items-center gap-2">
            <input v-model="importAllClearFirst" type="checkbox" id="clear-first"
              class="rounded border-gray-300 text-primary-600 focus:ring-primary-500" />
            <label for="clear-first" class="text-sm text-gray-600">匯入前先清空資料表</label>
          </div>
          <p v-if="importAllResult" class="text-sm text-green-700 bg-green-50 rounded-lg p-3">{{ importAllResult }}</p>
          <div v-if="importAllErrors.length" class="text-sm bg-red-50 border border-red-200 rounded-lg p-3 space-y-1">
            <p class="font-semibold text-red-700">匯入失敗明細：</p>
            <ul class="list-disc list-inside space-y-0.5">
              <li v-for="e in importAllErrors" :key="e.table" class="text-red-600">
                <span class="font-medium">{{ e.table }}</span>：{{ e.messages.join('；') }}
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>

    <p v-if="error" role="alert" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ error }}</p>

    <!-- Reset confirmation modal -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition duration-200 ease-out"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition duration-150 ease-in"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0">
        <div v-if="showResetModal" class="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div class="absolute inset-0 bg-black/50" @click="cancelReset"></div>
          <div class="relative bg-white rounded-xl shadow-xl max-w-md w-full p-6 space-y-4">
            <h3 class="text-lg font-semibold text-gray-900">確認清空資料庫</h3>
            <p class="text-sm text-gray-600">此操作會刪除所有資料（Admin 帳號會保留），無法復原。</p>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">
                請輸入「RESET」以確認
              </label>
              <input v-model="resetConfirmText" type="text" autocomplete="off"
                class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-red-500 focus:border-red-500 outline-none transition"
                placeholder="RESET" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">
                請輸入 Admin 密碼以完成二次驗證
              </label>
              <input v-model="resetPassword" type="password" autocomplete="current-password"
                class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-red-500 focus:border-red-500 outline-none transition"
                placeholder="Admin 密碼" @keyup.enter="confirmResetFromModal" />
            </div>
            <p v-if="resetModalError" class="text-sm text-danger">{{ resetModalError }}</p>
            <div class="flex justify-end gap-3">
              <button @click="cancelReset"
                class="bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-lg px-4 py-2 text-sm font-medium transition-colors">
                取消
              </button>
              <button @click="confirmResetFromModal" :disabled="resetting || inCooldown"
                class="bg-red-600 hover:bg-red-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
                {{ resetting ? '清空中...' : inCooldown ? '冷卻中...' : '確認清空' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { adminApi } from '@/api/admin'
import { useToastStore } from '@/stores/toast'
import PageHeader from '@/components/common/PageHeader.vue'

const toast = useToastStore()

const tables = [
  'users', 'tutors', 'students', 'subjects', 'tutor_subjects',
  'tutor_availability', 'matches', 'sessions', 'session_edit_logs',
  'exams', 'reviews', 'conversations', 'messages',
]

const users = ref([])
const loadingUsers = ref(false)
const seeding = ref(false)
const seedResult = ref('')
const resetting = ref(false)
const resetResult = ref('')
// Client-side throttle for the two-step reset flow. The backend already rate-
// limits /admin/reset/*, but a cooldown here avoids burning a rate-limit
// token on a stuck UI (e.g. admin double-clicking after a network blip) and
// gives a clearer UX message than a generic 429. 30s is enough to absorb
// accidental repeats without frustrating a legitimate retry.
const RESET_COOLDOWN_MS = 30_000
const lastResetAttemptAt = ref(0)
const systemStatus = ref(null)
const loadingStatus = ref(false)
const error = ref('')

const exportTable = ref('users')
const importTable = ref('users')
const importing = ref(false)
const importResult = ref('')
const fileInput = ref(null)
const importingAll = ref(false)
const importAllResult = ref('')
const importAllErrors = ref([])
const importAllClearFirst = ref(false)
const zipFileInput = ref(null)

const exporting = ref(false)
const exportingAll = ref(false)

const showResetModal = ref(false)
const resetConfirmText = ref('')
const resetPassword = ref('')
const resetModalError = ref('')
const inCooldown = ref(false)
// Persists the token from requestReset() so confirmReset() can be retried if
// it times out or fails without requiring a new requestReset() call.
const pendingResetToken = ref('')

function clearResults() {
  seedResult.value = ''
  importResult.value = ''
  importAllResult.value = ''
  importAllErrors.value = []
  resetResult.value = ''
  error.value = ''
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function fetchUsers() {
  loadingUsers.value = true
  error.value = ''
  try {
    users.value = await adminApi.listUsers()
  } catch (e) {
    error.value = e.message
  } finally {
    loadingUsers.value = false
  }
}

async function fetchSystemStatus() {
  loadingStatus.value = true
  error.value = ''
  try {
    systemStatus.value = await adminApi.getSystemStatus()
  } catch (e) {
    error.value = e.message
  } finally {
    loadingStatus.value = false
  }
}

async function handleSeed() {
  seeding.value = true
  clearResults()
  try {
    const result = await adminApi.seedData()
    if (result.skipped) {
      seedResult.value = result.message
    } else {
      seedResult.value = '假資料生成完成！'
    }
    await Promise.all([fetchUsers(), fetchSystemStatus()])
  } catch (e) {
    error.value = e.message
  } finally {
    seeding.value = false
  }
}

function handleReset() {
  // H-04: open a modal instead of window.prompt() so the password is masked.
  resetConfirmText.value = ''
  resetPassword.value = ''
  resetModalError.value = ''
  showResetModal.value = true
}

function cancelReset() {
  showResetModal.value = false
  resetConfirmText.value = ''
  resetPassword.value = ''
  resetModalError.value = ''
  pendingResetToken.value = ''
  inCooldown.value = false
  toast.info('已取消清空資料庫')
}

async function confirmResetFromModal() {
  if (resetting.value || inCooldown.value) return
  resetModalError.value = ''
  const sinceLast = Date.now() - lastResetAttemptAt.value
  if (lastResetAttemptAt.value && sinceLast < RESET_COOLDOWN_MS) {
    const remaining = RESET_COOLDOWN_MS - sinceLast
    const wait = Math.ceil(remaining / 1000)
    resetModalError.value = `請稍候 ${wait} 秒後再試`
    inCooldown.value = true
    setTimeout(() => { inCooldown.value = false }, remaining)
    return
  }
  if (resetConfirmText.value !== 'RESET') {
    resetModalError.value = '請輸入正確的確認文字「RESET」'
    return
  }
  if (!resetPassword.value) {
    resetModalError.value = '請輸入 Admin 密碼'
    return
  }
  lastResetAttemptAt.value = Date.now()
  resetting.value = true
  clearResults()
  try {
    // Reuse the token from a prior attempt that failed at the confirmReset step
    // so the admin can retry the password without restarting the whole flow.
    if (!pendingResetToken.value) {
      const { reset_token } = await adminApi.requestReset()
      pendingResetToken.value = reset_token
    }
    const result = await adminApi.confirmReset(pendingResetToken.value, resetPassword.value)
    pendingResetToken.value = ''
    const deleted = result?.deleted || {}
    const total = Object.values(deleted).reduce((a, v) => a + (Number(v) || 0), 0)
    resetResult.value = result?.backup
      ? `已清空 ${total} 筆資料；備份：${result.backup}`
      : `已清空 ${total} 筆資料`
    toast.success('資料庫已清空')
    showResetModal.value = false
    resetPassword.value = ''
    resetConfirmText.value = ''
    await Promise.all([fetchUsers(), fetchSystemStatus()])
  } catch (e) {
    // Keep modal open so the user can correct and retry.
    // If a token is held, the confirm step failed — let the user retry the password.
    resetModalError.value = pendingResetToken.value
      ? e.message + '；請重試密碼確認'
      : e.message
    resetPassword.value = ''
  } finally {
    resetting.value = false
  }
}

async function drillTable(tableName) {
  exporting.value = true
  clearResults()
  try {
    const blob = await adminApi.exportCsv(tableName)
    downloadBlob(blob, `${tableName}.csv`)
    toast.success(`已匯出 ${tableName}`)
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  } finally {
    exporting.value = false
  }
}

async function handleExport() {
  exporting.value = true
  clearResults()
  try {
    const blob = await adminApi.exportCsv(exportTable.value)
    downloadBlob(blob, `${exportTable.value}.csv`)
  } catch (e) {
    error.value = e.message
  } finally {
    exporting.value = false
  }
}

async function handleExportAll() {
  exportingAll.value = true
  clearResults()
  try {
    const blob = await adminApi.exportAll()
    downloadBlob(blob, 'all_tables.zip')
  } catch (e) {
    error.value = e.message
  } finally {
    exportingAll.value = false
  }
}

async function handleImportAll() {
  const file = zipFileInput.value?.files?.[0]
  if (!file) {
    error.value = '請選擇 ZIP 檔案'
    return
  }
  importingAll.value = true
  clearResults()
  try {
    const formData = new FormData()
    formData.append('file', file)
    const result = await adminApi.importAll(formData, importAllClearFirst.value)
    const imported = result?.imported || {}
    const errors = result?.errors || {}
    const tableCount = Object.keys(imported).length
    const totalRows = Object.values(imported).reduce((a, b) => a + (Number(b) || 0), 0)
    const errorCount = Object.values(errors).reduce((a, v) => a + (Array.isArray(v) ? v.length : 1), 0)
    importAllResult.value = `已匯入 ${tableCount} 張資料表，共 ${totalRows} 筆資料`
      + (errorCount ? `（${errorCount} 筆失敗）` : '')
    importAllErrors.value = Object.entries(errors).map(([table, errs]) => ({
      table,
      messages: Array.isArray(errs) ? errs : [String(errs)],
    }))
    if (zipFileInput.value) zipFileInput.value.value = ''
    await fetchUsers()
  } catch (e) {
    error.value = e.message
  } finally {
    importingAll.value = false
  }
}

async function handleImport() {
  const file = fileInput.value?.files?.[0]
  if (!file) {
    error.value = '請選擇 CSV 檔案'
    return
  }
  importing.value = true
  clearResults()
  try {
    const formData = new FormData()
    formData.append('file', file)
    const result = await adminApi.importCsv(formData, importTable.value)
    importResult.value = `已匯入 ${result.count} 筆資料`
    if (fileInput.value) fileInput.value.value = ''
    await fetchUsers()
  } catch (e) {
    error.value = e.message
  } finally {
    importing.value = false
  }
}

onMounted(() => {
  fetchUsers()
  fetchSystemStatus()
})
</script>
