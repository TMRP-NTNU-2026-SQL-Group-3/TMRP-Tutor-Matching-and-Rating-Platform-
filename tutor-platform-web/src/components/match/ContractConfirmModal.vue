<template>
  <Transition
    enter-active-class="transition duration-200 ease-out"
    enter-from-class="opacity-0"
    enter-to-class="opacity-100"
    leave-active-class="transition duration-150 ease-in"
    leave-from-class="opacity-100"
    leave-to-class="opacity-0">
    <div v-if="visible" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
         role="dialog" aria-modal="true" aria-labelledby="contract-confirm-title"
         @click.self="$emit('cancel')" @keydown="onKeydown">
      <div ref="dialogEl" class="bg-white rounded-xl shadow-xl w-full max-w-md p-6 space-y-4">
        <h3 id="contract-confirm-title" class="text-lg font-semibold text-gray-900">確認正式合作條件</h3>
        <p class="text-sm text-gray-500">請確認以下合約條件，雙方同意後正式開始上課。</p>

        <div class="grid grid-cols-1 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">每小時費用 *</label>
            <input ref="firstFieldEl" v-model.number="form.hourly_rate" type="number" required min="1" max="99999" step="1"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">每週堂數 *</label>
            <input v-model.number="form.sessions_per_week" type="number" required min="1" step="1"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">正式起始日 *</label>
            <input v-model="form.start_date" type="date" required
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
          </div>
        </div>

        <p v-if="localError" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ localError }}</p>

        <div class="flex justify-end gap-3">
          <button @click="$emit('cancel')" :disabled="submitting"
            class="bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
            取消
          </button>
          <button @click="handleSubmit" :disabled="submitting"
            class="bg-green-600 hover:bg-green-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
            {{ submitting ? '送出中...' : '確認合約' }}
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { reactive, ref, watch, nextTick } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  submitting: { type: Boolean, default: false },
  defaults: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['submit', 'cancel'])

const localError = ref('')
const form = reactive({
  hourly_rate: null,
  sessions_per_week: null,
  start_date: '',
})

// 2.5 A11y: refs used to move focus into the dialog on open and trap Tab.
const dialogEl = ref(null)
const firstFieldEl = ref(null)
let previouslyFocused = null

function todayIso() {
  return new Date().toISOString().slice(0, 10)
}

// Esc closes; Tab cycles within the dialog so keyboard users stay in-modal.
function onKeydown(event) {
  if (event.key === 'Escape' && !props.submitting) {
    event.stopPropagation()
    emit('cancel')
    return
  }
  if (event.key !== 'Tab' || !dialogEl.value) return
  const focusables = dialogEl.value.querySelectorAll(
    'input, button, select, textarea, [href], [tabindex]:not([tabindex="-1"])',
  )
  const visible = Array.from(focusables).filter(el => !el.disabled && el.offsetParent !== null)
  if (!visible.length) return
  const first = visible[0]
  const last = visible[visible.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(() => props.visible, (v) => {
  if (v) {
    localError.value = ''
    form.hourly_rate = props.defaults.hourly_rate ?? null
    form.sessions_per_week = props.defaults.sessions_per_week ?? null
    form.start_date = props.defaults.start_date || todayIso()
    if (typeof document !== 'undefined') {
      previouslyFocused = document.activeElement
    }
    nextTick(() => firstFieldEl.value?.focus())
  } else if (previouslyFocused && typeof previouslyFocused.focus === 'function') {
    // Restore focus to whatever had it before the modal opened so keyboard
    // users don't get stranded at the top of the document.
    previouslyFocused.focus()
    previouslyFocused = null
  }
})

function handleSubmit() {
  localError.value = ''
  if (form.hourly_rate == null || form.hourly_rate <= 0 || form.hourly_rate > 99999) {
    localError.value = '時薪必須介於 1 至 99,999 之間'
    return
  }
  if (form.sessions_per_week == null || form.sessions_per_week < 1) {
    localError.value = '每週堂數至少為 1'
    return
  }
  if (!form.start_date) {
    localError.value = '請選擇起始日'
    return
  }
  emit('submit', { ...form })
}
</script>
