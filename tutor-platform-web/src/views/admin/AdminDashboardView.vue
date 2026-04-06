<template>
  <div>
    <PageHeader title="管理後台" />

    <!-- Seed data -->
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-6">
      <h2 class="text-lg font-semibold text-gray-900 mb-3">假資料生成</h2>
      <button @click="handleSeed" :disabled="seeding"
        class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
        {{ seeding ? '生成中...' : '生成假資料' }}
      </button>
      <p v-if="seedResult" class="text-sm text-green-700 bg-green-50 rounded-lg p-3 mt-3">{{ seedResult }}</p>
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
      <div v-if="users.length" class="overflow-x-auto">
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
        </div>
      </div>
    </div>

    <p v-if="error" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { adminApi } from '@/api/admin'
import { useAuthStore } from '@/stores/auth'
import PageHeader from '@/components/common/PageHeader.vue'

const tables = [
  'Users', 'Tutors', 'Students', 'Subjects', 'Tutor_Subjects',
  'Tutor_Availability', 'Matches', 'Sessions', 'Session_Edit_Logs',
  'Exams', 'Reviews', 'Conversations', 'Messages',
]

const users = ref([])
const loadingUsers = ref(false)
const seeding = ref(false)
const seedResult = ref('')
const error = ref('')

const exportTable = ref('Users')
const importTable = ref('Users')
const importing = ref(false)
const importResult = ref('')
const fileInput = ref(null)
const importingAll = ref(false)
const importAllResult = ref('')
const importAllClearFirst = ref(false)
const zipFileInput = ref(null)

const exporting = ref(false)
const exportingAll = ref(false)
const auth = useAuthStore()

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

async function handleSeed() {
  seeding.value = true
  seedResult.value = ''
  error.value = ''
  try {
    const result = await adminApi.seedData()
    if (result.skipped) {
      seedResult.value = result.message
    } else {
      seedResult.value = '假資料生成完成！'
    }
    await fetchUsers()
  } catch (e) {
    error.value = e.message
  } finally {
    seeding.value = false
  }
}

async function handleExport() {
  exporting.value = true
  error.value = ''
  try {
    const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
    const res = await fetch(`${apiBase}/api/admin/export/${exportTable.value}`, {
      headers: { Authorization: `Bearer ${auth.token}` }
    })
    if (!res.ok) {
      const body = await res.json().catch(() => null)
      throw new Error(body?.message || '匯出失敗')
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${exportTable.value}.csv`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    error.value = e.message
  } finally {
    exporting.value = false
  }
}

async function handleExportAll() {
  exportingAll.value = true
  error.value = ''
  try {
    const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
    const res = await fetch(`${apiBase}/api/admin/export-all`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${auth.token}` }
    })
    if (!res.ok) {
      const body = await res.json().catch(() => null)
      throw new Error(body?.message || '匯出失敗')
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'all_tables.zip'
    a.click()
    URL.revokeObjectURL(url)
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
  importAllResult.value = ''
  error.value = ''
  try {
    const formData = new FormData()
    formData.append('file', file)
    const result = await adminApi.importAll(formData, importAllClearFirst.value)
    const tableCount = Object.keys(result).length
    const totalRows = Object.values(result).filter(v => typeof v === 'number').reduce((a, b) => a + b, 0)
    importAllResult.value = `已匯入 ${tableCount} 張資料表，共 ${totalRows} 筆資料`
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
  importResult.value = ''
  error.value = ''
  try {
    const formData = new FormData()
    formData.append('file', file)
    const result = await adminApi.importCsv(formData, importTable.value)
    importResult.value = `已匯入 ${result.count} 筆資料`
  } catch (e) {
    error.value = e.message
  } finally {
    importing.value = false
  }
}

onMounted(fetchUsers)
</script>
