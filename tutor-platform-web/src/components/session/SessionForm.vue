<template>
  <Transition
    enter-active-class="transition duration-200 ease-out"
    enter-from-class="opacity-0 -translate-y-2"
    enter-to-class="opacity-100 translate-y-0"
    leave-active-class="transition duration-150 ease-in"
    leave-from-class="opacity-100 translate-y-0"
    leave-to-class="opacity-0 -translate-y-2">
    <div v-if="visible" class="bg-gray-50 rounded-xl p-5 mb-4 space-y-4">
      <h3 class="font-semibold text-gray-900">新增上課紀錄</h3>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">日期 *</label>
          <input v-model="form.session_date" type="date" :max="today"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">時數 *</label>
          <input v-model.number="form.hours" type="number" min="0.5" max="24" step="0.5"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
        </div>
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">教學內容 *</label>
        <textarea v-model="form.content_summary" rows="3"
          class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition"></textarea>
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">指派作業</label>
        <textarea v-model="form.homework" rows="2"
          class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition"></textarea>
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">學生表現</label>
        <textarea v-model="form.student_performance" rows="2"
          class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition"></textarea>
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">下次計畫</label>
        <textarea v-model="form.next_plan" rows="2"
          class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition"></textarea>
      </div>
      <div class="flex items-center gap-2">
        <input v-model="form.visible_to_parent" type="checkbox" id="session-visible"
          class="rounded border-gray-300 text-primary-600 focus:ring-primary-500" />
        <label for="session-visible" class="text-sm text-gray-700">家長可見</label>
      </div>
      <p v-if="error" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ error }}</p>
      <div class="flex gap-3">
        <button @click="handleSubmit" :disabled="submitting"
          class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
          {{ submitting ? '新增中...' : '確認新增' }}
        </button>
        <button @click="$emit('cancel')"
          class="bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-lg px-4 py-2 text-sm font-medium transition-colors">
          取消
        </button>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { reactive, computed } from 'vue'

defineProps({
  visible: { type: Boolean, default: false },
  submitting: { type: Boolean, default: false },
  error: { type: String, default: '' },
})

const emit = defineEmits(['submit', 'cancel'])

// Clamp the date picker to today so tutors can't log future sessions.
const today = computed(() => {
  const d = new Date()
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
})

const form = reactive({
  session_date: '',
  hours: 2,
  content_summary: '',
  homework: '',
  student_performance: '',
  next_plan: '',
  visible_to_parent: true,
})

function handleSubmit() {
  emit('submit', {
    session_date: form.session_date,
    hours: form.hours,
    content_summary: form.content_summary,
    homework: form.homework || null,
    student_performance: form.student_performance || null,
    next_plan: form.next_plan || null,
    visible_to_parent: form.visible_to_parent,
  })
}

function reset() {
  form.session_date = ''
  form.hours = 2
  form.content_summary = ''
  form.homework = ''
  form.student_performance = ''
  form.next_plan = ''
  form.visible_to_parent = true
}

defineExpose({ reset })
</script>
