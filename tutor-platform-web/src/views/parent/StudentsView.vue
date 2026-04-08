<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-gray-900">管理子女</h1>
      <button v-if="!showForm" @click="showForm = true"
        class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors">
        + 新增子女
      </button>
    </div>

    <div v-if="loading" class="text-center py-8 text-gray-500">載入中...</div>

    <div v-else>
      <!-- Student table -->
      <div v-if="students.length" class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="bg-gray-50 border-b border-gray-200">
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">姓名</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">學校</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">年級</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <tr v-for="s in students" :key="s.student_id" class="hover:bg-gray-50 transition-colors">
              <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ s.name }}</td>
              <td class="px-4 py-3 text-sm text-gray-500">{{ s.school || '-' }}</td>
              <td class="px-4 py-3 text-sm text-gray-500">{{ s.grade || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <EmptyState v-else message="尚未新增子女" />

      <!-- Add form -->
      <Transition
        enter-active-class="transition duration-200 ease-out"
        enter-from-class="opacity-0 -translate-y-2"
        enter-to-class="opacity-100 translate-y-0"
        leave-active-class="transition duration-150 ease-in"
        leave-from-class="opacity-100 translate-y-0"
        leave-to-class="opacity-0 -translate-y-2">
        <div v-if="showForm" class="bg-gray-50 rounded-xl p-6 mt-6 space-y-4">
          <h3 class="text-lg font-semibold text-gray-900">新增子女</h3>
          <form @submit.prevent="handleAdd" class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">姓名 *</label>
              <input v-model="form.name" type="text" required
                class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">學校</label>
                <input v-model="form.school" type="text"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">年級</label>
                <input v-model="form.grade" type="text"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
              </div>
            </div>
            <p v-if="error" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ error }}</p>
            <div class="flex gap-3">
              <button type="submit" :disabled="adding"
                class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
                {{ adding ? '新增中...' : '確認新增' }}
              </button>
              <button type="button" @click="showForm = false"
                class="bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-lg px-4 py-2 text-sm font-medium transition-colors">
                取消
              </button>
            </div>
          </form>
        </div>
      </Transition>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch, onMounted } from 'vue'
import { studentsApi } from '@/api/students'
import EmptyState from '@/components/common/EmptyState.vue'

const students = ref([])
const loading = ref(false)
const showForm = ref(false)
const adding = ref(false)
const error = ref('')
const form = reactive({ name: '', school: '', grade: '' })

// 表單開啟時清除之前的錯誤訊息
watch(showForm, (v) => { if (v) error.value = '' })

async function fetchStudents() {
  loading.value = true
  try {
    students.value = await studentsApi.list()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function handleAdd() {
  error.value = ''
  adding.value = true
  try {
    await studentsApi.add(form)
    form.name = ''
    form.school = ''
    form.grade = ''
    showForm.value = false
    await fetchStudents()
  } catch (e) {
    error.value = e.message
  } finally {
    adding.value = false
  }
}

onMounted(fetchStudents)
</script>
