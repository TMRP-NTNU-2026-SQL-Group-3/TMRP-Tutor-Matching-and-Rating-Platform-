<template>
  <Transition
    enter-active-class="transition duration-200 ease-out"
    enter-from-class="opacity-0 -translate-y-2"
    enter-to-class="opacity-100 translate-y-0"
    leave-active-class="transition duration-150 ease-in"
    leave-from-class="opacity-100 translate-y-0"
    leave-to-class="opacity-0 -translate-y-2">
    <div v-if="visible" class="bg-gray-50 rounded-xl p-6 space-y-4">
      <h3 class="text-lg font-semibold text-gray-900">撰寫評價</h3>

      <!-- 評價對象選擇（多選時顯示） -->
      <div v-if="reviewTypes.length > 1">
        <label class="block text-sm font-medium text-gray-700 mb-1">評價對象</label>
        <select v-model="form.review_type"
          class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition">
          <option v-for="t in reviewTypes" :key="t.value" :value="t.value">{{ t.label }}</option>
        </select>
      </div>

      <!-- 四維度評分 -->
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div v-for="(label, idx) in dimensionLabels" :key="idx">
          <label class="block text-sm font-medium text-gray-700 mb-1">{{ label }}（1-5）</label>
          <input v-model.number="form['rating_' + (idx + 1)]" type="number" min="1" max="5"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
        </div>
      </div>

      <!-- 文字評語 -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">個性評語</label>
        <textarea v-model="form.personality_comment" rows="2"
          class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition"></textarea>
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">評語</label>
        <textarea v-model="form.comment" rows="2"
          class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition"></textarea>
      </div>

      <p v-if="error" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ error }}</p>

      <div class="flex gap-3">
        <button @click="handleSubmit" :disabled="submitting"
          class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
          {{ submitting ? '提交中...' : '提交評價' }}
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
import { reactive, computed, watch } from 'vue'

const LABEL_MAP = {
  parent_to_tutor: ['教學能力', '溝通態度', '準時出席', '整體滿意度'],
  tutor_to_parent: ['配合度', '溝通態度', '準時付費', '整體滿意度'],
  tutor_to_student: ['學習態度', '完成作業', '課堂表現', '整體進步'],
}

const props = defineProps({
  visible: { type: Boolean, default: false },
  reviewTypes: {
    type: Array,
    default: () => [{ value: 'parent_to_tutor', label: '評價老師' }],
  },
  matchId: { type: Number, required: true },
  submitting: { type: Boolean, default: false },
  error: { type: String, default: '' },
})

const emit = defineEmits(['submit', 'cancel'])

const form = reactive({
  review_type: props.reviewTypes[0]?.value || 'parent_to_tutor',
  rating_1: 5,
  rating_2: 5,
  rating_3: 5,
  rating_4: 5,
  personality_comment: '',
  comment: '',
})

watch(
  () => props.reviewTypes,
  (types) => {
    if (types.length && !form.review_type) {
      form.review_type = types[0].value
    }
  },
  { immediate: true }
)

const dimensionLabels = computed(() => LABEL_MAP[form.review_type] || LABEL_MAP.parent_to_tutor)

function handleSubmit() {
  emit('submit', {
    match_id: props.matchId,
    ...form,
  })
}
</script>
