import { ref, shallowRef } from 'vue'

const _visible = ref(false)
const _options = shallowRef({ title: '', message: '', confirmLabel: '確認', destructive: true })
let _resolve = null

// Internal state consumed only by ConfirmDialog.vue — not part of the caller-facing API.
export const confirmDialogState = {
  visible: _visible,
  options: _options,
  accept() {
    _visible.value = false
    _resolve?.(true)
    _resolve = null
  },
  cancel() {
    _visible.value = false
    _resolve?.(false)
    _resolve = null
  },
}

export function useConfirm() {
  return {
    confirm(opts) {
      _options.value = typeof opts === 'string'
        ? { title: opts, message: '', confirmLabel: '確認', destructive: true }
        : { title: '', message: '', confirmLabel: '確認', destructive: true, ...opts }
      _visible.value = true
      return new Promise(resolve => { _resolve = resolve })
    },
  }
}
