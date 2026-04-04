import { defineStore } from 'pinia'
import { ref } from 'vue'

let _id = 0

export const useToastStore = defineStore('toast', () => {
  const toasts = ref([])

  function _add(type, message, duration = 3000) {
    const id = ++_id
    toasts.value.push({ id, type, message })
    if (duration > 0) {
      setTimeout(() => remove(id), duration)
    }
  }

  function remove(id) {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }

  const success = (msg) => _add('success', msg)
  const error = (msg) => _add('error', msg, 5000)
  const warning = (msg) => _add('warning', msg, 4000)
  const info = (msg) => _add('info', msg)

  return { toasts, remove, success, error, warning, info }
})
