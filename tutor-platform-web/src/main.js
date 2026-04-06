import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './style.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)

// F1: 全域錯誤處理 — 攔截元件中未處理的錯誤
app.config.errorHandler = (err, instance, info) => {
  console.error('[Vue Error]', err, info)
}

// 攔截未處理的 Promise rejection
window.addEventListener('unhandledrejection', (event) => {
  console.error('[Unhandled Rejection]', event.reason)
})

app.mount('#app')
