<template>
  <Transition
    enter-active-class="transition duration-200 ease-out"
    enter-from-class="opacity-0 -translate-y-2"
    enter-to-class="opacity-100 translate-y-0"
    leave-active-class="transition duration-150 ease-in"
    leave-from-class="opacity-100 translate-y-0"
    leave-to-class="opacity-0 -translate-y-2">
    <div v-if="visible" class="bg-gray-50 rounded-xl p-6 space-y-4">
      <h3 class="text-lg font-semibold text-gray-900">建立媒合邀請</h3>
      <div class="grid md:grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">選擇子女 *</label>
          <select v-model="form.student_id" required
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition">
            <option :value="null" disabled>請選擇</option>
            <option v-for="s in students" :key="s.student_id" :value="s.student_id">
              {{ s.name }}
            </option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">科目 *</label>
          <select v-model="form.subject_id" required
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition">
            <option :value="null" disabled>請選擇</option>
            <option v-for="s in subjects" :key="s.subject_id" :value="s.subject_id">
              {{ s.subject_name }} (${{ s.hourly_rate }}/hr)
            </option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">每小時費用 *</label>
          <input v-model.number="form.hourly_rate" type="number" min="0"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">每週堂數 *</label>
          <input v-model.number="form.sessions_per_week" type="number" min="1"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
        </div>
      </div>
      <div class="flex items-center gap-2">
        <input v-model="form.want_trial" type="checkbox" id="want-trial"
          class="rounded border-gray-300 text-primary-600 focus:ring-primary-500" />
        <label for="want-trial" class="text-sm text-gray-700">希望先試教</label>
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">備註</label>
        <textarea v-model="form.invite_message" rows="3"
          class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition"></textarea>
      </div>
      <p v-if="error" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ error }}</p>
      <div class="flex gap-3">
        <button @click="$emit('submit', { ...form })" :disabled="submitting"
          class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
          {{ submitting ? '送出中...' : '送出邀請' }}
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
import { reactive } from 'vue'

defineProps({
  visible: { type: Boolean, default: false },
  students: { type: Array, default: () => [] },
  subjects: { type: Array, default: () => [] },
  submitting: { type: Boolean, default: false },
  error: { type: String, default: '' },
})

defineEmits(['submit', 'cancel'])

const form = reactive({
  student_id: null,
  subject_id: null,
  hourly_rate: 0,
  sessions_per_week: 1,
  want_trial: false,
  invite_message: '',
})
</script>
