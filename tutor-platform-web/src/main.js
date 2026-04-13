import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useToastStore } from '@/stores/toast'
import './style.css'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)

// F-16 / F1: global error handler — catch uncaught render/lifecycle errors and
// surface them to the user via a toast instead of silently blanking the page.
// Toast store is resolved lazily per-call so it works regardless of mount order.
function notifyUnexpectedError() {
  try {
    useToastStore().error('發生未預期錯誤，請稍後再試')
  } catch {
    // Pinia not ready yet (e.g. error during bootstrap) — swallow the toast.
  }
}

app.config.errorHandler = (err, instance, info) => {
  console.error('[Vue Error]', err, info)
  notifyUnexpectedError()
}

window.addEventListener('unhandledrejection', (event) => {
  console.error('[Unhandled Rejection]', event.reason)
  notifyUnexpectedError()
})

window.addEventListener('error', (event) => {
  console.error('[Window Error]', event.error || event.message)
  notifyUnexpectedError()
})

app.mount('#app')
