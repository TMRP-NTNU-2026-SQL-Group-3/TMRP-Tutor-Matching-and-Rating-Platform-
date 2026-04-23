<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-gray-900">管理子女</h1>
      <button v-if="!showForm && editingId == null" @click="openAddForm"
        class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors">
        + 新增子女
      </button>
    </div>

    <div v-if="loading" class="text-center py-8 text-gray-500">載入中...</div>

    <div v-else>
      <p v-if="error && !showForm" role="alert" class="text-sm text-danger bg-red-50 rounded-lg p-3 mb-4">{{ error }}</p>

      <!-- Student table -->
      <div v-if="students.length" class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-x-auto">
        <table class="w-full">
          <thead>
            <tr class="bg-gray-50 border-b border-gray-200">
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">姓名</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">學校</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">年級</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <tr v-for="s in students" :key="s.student_id" class="hover:bg-gray-50 transition-colors">
              <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ s.name }}</td>
              <td class="px-4 py-3 text-sm text-gray-500">{{ s.school || '-' }}</td>
              <td class="px-4 py-3 text-sm text-gray-500">{{ s.grade || '-' }}</td>
              <td class="px-4 py-3 text-sm text-right">
                <button @click="openEditForm(s)"
                  class="text-primary-600 hover:text-primary-700 font-medium transition-colors">編輯</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <EmptyState v-else-if="!error" message="尚未新增子女" />

      <!-- Add / edit form -->
      <Transition
        enter-active-class="transition duration-200 ease-out"
        enter-from-class="opacity-0 -translate-y-2"
        enter-to-class="opacity-100 translate-y-0"
        leave-active-class="transition duration-150 ease-in"
        leave-from-class="opacity-100 translate-y-0"
        leave-to-class="opacity-0 -translate-y-2">
        <div v-if="showForm" class="bg-gray-50 rounded-xl p-6 mt-6 space-y-4">
          <h3 class="text-lg font-semibold text-gray-900">{{ editingId == null ? '新增子女' : '編輯子女資料' }}</h3>
          <form @submit.prevent="handleSubmit" class="space-y-4">
            <div>
              <label for="student-name" class="block text-sm font-medium text-gray-700 mb-1">姓名 *</label>
              <input id="student-name" v-model="form.name" type="text" required
                :aria-invalid="!!nameError || null" aria-describedby="student-form-error"
                class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label for="student-school" class="block text-sm font-medium text-gray-700 mb-1">學校</label>
                <input id="student-school" v-model="form.school" type="text"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
              </div>
              <div>
                <label for="student-grade" class="block text-sm font-medium text-gray-700 mb-1">年級</label>
                <input id="student-grade" v-model="form.grade" type="text"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
              </div>
            </div>
            <p v-if="nameError" id="student-form-error" role="alert" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ nameError }}</p>
            <p v-else-if="error" id="student-form-error" role="alert" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ error }}</p>
            <div class="flex gap-3">
              <button type="submit" :disabled="submitting"
                class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
                {{ submitting ? '儲存中...' : (editingId == null ? '確認新增' : '儲存變更') }}
              </button>
              <button type="button" @click="closeForm"
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
import { useToastStore } from '@/stores/toast'
import EmptyState from '@/components/common/EmptyState.vue'

const toast = useToastStore()

const students = ref([])
const loading = ref(false)
const showForm = ref(false)
const submitting = ref(false)
const error = ref('')
const nameError = ref('')
const editingId = ref(null)
const form = reactive({ name: '', school: '', grade: '' })

// Clear previous errors when the form reopens so stale messages don't linger.
watch(showForm, (v) => {
  if (v) {
    error.value = ''
    nameError.value = ''
  }
})

async function fetchStudents() {
  loading.value = true
  error.value = ''
  try {
    students.value = await studentsApi.list()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.name = ''
  form.school = ''
  form.grade = ''
  editingId.value = null
  nameError.value = ''
}

function openAddForm() {
  resetForm()
  showForm.value = true
}

function openEditForm(student) {
  editingId.value = student.student_id
  form.name = student.name || ''
  form.school = student.school || ''
  form.grade = student.grade || ''
  showForm.value = true
}

function closeForm() {
  showForm.value = false
  resetForm()
}

async function handleSubmit() {
  error.value = ''
  nameError.value = ''
  if (!form.name?.trim()) {
    nameError.value = '姓名為必填'
    return
  }
  submitting.value = true
  try {
    const payload = {
      name: form.name.trim(),
      school: form.school?.trim() || null,
      grade: form.grade?.trim() || null,
    }
    if (editingId.value == null) {
      await studentsApi.add(payload)
      toast.success('子女已新增')
    } else {
      await studentsApi.update(editingId.value, payload)
      toast.success('子女資料已更新')
    }
    closeForm()
    await fetchStudents()
  } catch (e) {
    error.value = e.message
    toast.error(e.message)
  } finally {
    submitting.value = false
  }
}

onMounted(fetchStudents)
</script>
