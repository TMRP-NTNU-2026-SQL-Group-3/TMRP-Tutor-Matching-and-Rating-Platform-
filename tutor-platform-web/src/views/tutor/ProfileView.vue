<template>
  <div>
    <PageHeader title="編輯個人檔案" />

    <div v-if="loading" class="text-center py-8 text-gray-500">載入中...</div>

    <form v-else @submit.prevent="handleSave" class="space-y-6">
      <!-- Intro & Experience -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-4">
        <h2 class="text-lg font-semibold text-gray-900">基本資訊</h2>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">自我介紹</label>
          <textarea v-model="form.self_intro" rows="4"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition"></textarea>
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">教學經驗</label>
          <textarea v-model="form.teaching_experience" rows="4"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition"></textarea>
        </div>
      </div>

      <!-- School info -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-4">
        <h2 class="text-lg font-semibold text-gray-900">學歷資訊</h2>
        <div class="grid md:grid-cols-3 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">大學</label>
            <input v-model="form.university" type="text"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
            <label class="flex items-center gap-2 mt-2 text-sm text-gray-600">
              <input v-model="form.show_university" type="checkbox"
                class="rounded border-gray-300 text-primary-600 focus:ring-primary-500" /> 公開
            </label>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">科系</label>
            <input v-model="form.department" type="text"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
            <label class="flex items-center gap-2 mt-2 text-sm text-gray-600">
              <input v-model="form.show_department" type="checkbox"
                class="rounded border-gray-300 text-primary-600 focus:ring-primary-500" /> 公開
            </label>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">年級</label>
            <input v-model.number="form.grade_year" type="number" min="1" max="10"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
            <label class="flex items-center gap-2 mt-2 text-sm text-gray-600">
              <input v-model="form.show_grade_year" type="checkbox"
                class="rounded border-gray-300 text-primary-600 focus:ring-primary-500" /> 公開
            </label>
          </div>
        </div>
      </div>

      <!-- Subjects -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-4">
        <h2 class="text-lg font-semibold text-gray-900">授課科目</h2>
        <div v-for="(item, idx) in subjectList" :key="idx" class="flex items-center gap-3">
          <select v-model="item.subject_id"
            class="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition">
            <option :value="null" disabled>選擇科目</option>
            <option v-for="s in allSubjects" :key="s.subject_id" :value="s.subject_id">
              {{ s.subject_name }}
            </option>
          </select>
          <div class="flex items-center gap-1">
            <span class="text-sm text-gray-500">$</span>
            <input v-model.number="item.hourly_rate" type="number" min="1" placeholder="時薪"
              class="w-24 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
            <span class="text-sm text-gray-500">/hr</span>
          </div>
          <button type="button" @click="subjectList.splice(idx, 1)"
            class="text-red-500 hover:text-red-700 text-sm font-medium transition-colors">移除</button>
        </div>
        <button type="button" @click="subjectList.push({ subject_id: null, hourly_rate: null })"
          class="text-primary-600 hover:text-primary-700 text-sm font-medium transition-colors">+ 新增科目</button>
      </div>

      <!-- Settings -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-4">
        <h2 class="text-lg font-semibold text-gray-900">偏好設定</h2>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">最大收生數</label>
          <input v-model.number="form.max_students" type="number" min="1" max="50"
            class="w-32 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
        </div>
        <div class="space-y-2">
          <label class="flex items-center gap-2 text-sm text-gray-600">
            <input v-model="form.show_hourly_rate" type="checkbox"
              class="rounded border-gray-300 text-primary-600 focus:ring-primary-500" />
            公開時薪
          </label>
          <label class="flex items-center gap-2 text-sm text-gray-600">
            <input v-model="form.show_subjects" type="checkbox"
              class="rounded border-gray-300 text-primary-600 focus:ring-primary-500" />
            公開授課科目
          </label>
        </div>
      </div>

      <!-- Messages -->
      <p v-if="error" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ error }}</p>
      <p v-if="success" class="text-sm text-green-700 bg-green-50 rounded-lg p-3">{{ success }}</p>

      <button type="submit" :disabled="saving"
        class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-6 py-2.5 text-sm font-medium transition-colors disabled:opacity-50">
        {{ saving ? '儲存中...' : '儲存' }}
      </button>
    </form>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { tutorsApi } from '@/api/tutors'
import { subjectsApi } from '@/api/subjects'
import PageHeader from '@/components/common/PageHeader.vue'

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const success = ref('')
const allSubjects = ref([])
const subjectList = ref([])

const form = reactive({
  self_intro: '',
  teaching_experience: '',
  university: '',
  department: '',
  grade_year: null,
  max_students: 5,
  show_university: true,
  show_department: true,
  show_grade_year: true,
  show_hourly_rate: true,
  show_subjects: true,
})

async function handleSave() {
  error.value = ''
  success.value = ''
  saving.value = true
  try {
    await tutorsApi.updateProfile(form)

    // 儲存科目設定
    const validSubjects = subjectList.value.filter(s => s.subject_id && s.hourly_rate)
    await tutorsApi.updateSubjects({ subjects: validSubjects })

    success.value = '個人檔案已更新'
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  loading.value = true
  try {
    const [detail, subjects] = await Promise.all([
      tutorsApi.getMyProfile(),
      subjectsApi.list(),
    ])

    form.self_intro = detail.self_intro || ''
    form.teaching_experience = detail.teaching_experience || ''
    form.university = detail.university || ''
    form.department = detail.department || ''
    form.grade_year = detail.grade_year || null
    form.max_students = detail.max_students || 5
    form.show_university = detail.show_university ?? true
    form.show_department = detail.show_department ?? true
    form.show_grade_year = detail.show_grade_year ?? true
    form.show_hourly_rate = detail.show_hourly_rate ?? true
    form.show_subjects = detail.show_subjects ?? true

    allSubjects.value = subjects
    subjectList.value = (detail.subjects || []).map(s => ({
      subject_id: s.subject_id,
      hourly_rate: s.hourly_rate,
    }))
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})
</script>
