<template>
  <Transition
    enter-active-class="transition duration-200 ease-out"
    enter-from-class="opacity-0 -translate-y-2"
    enter-to-class="opacity-100 translate-y-0"
    leave-active-class="transition duration-150 ease-in"
    leave-from-class="opacity-100 translate-y-0"
    leave-to-class="opacity-0 -translate-y-2">
    <div v-if="visible" class="bg-gray-50 rounded-xl p-6 mb-6 space-y-3">
      <label class="block text-sm font-medium text-gray-700">{{ label }} *</label>
      <textarea v-model="reason" rows="3"
        class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition"></textarea>
      <div class="flex gap-3">
        <button @click="$emit('submit', reason)" :disabled="!reason.trim()"
          class="bg-red-600 hover:bg-red-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
          {{ submitText }}
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
import { ref } from 'vue'

defineProps({
  visible: { type: Boolean, default: false },
  label: { type: String, default: '終止原因' },
  submitText: { type: String, default: '確認終止' },
})

defineEmits(['submit', 'cancel'])

const reason = ref('')
</script>
