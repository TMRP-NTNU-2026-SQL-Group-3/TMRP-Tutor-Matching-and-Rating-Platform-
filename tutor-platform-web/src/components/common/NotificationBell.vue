<template>
  <div ref="rootEl" class="relative">
    <button
      @click="toggle"
      aria-label="通知"
      class="relative p-1.5 rounded-lg text-gray-500 hover:text-primary-600 hover:bg-primary-50 bg-transparent transition-colors">
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
      </svg>
      <span v-if="store.unreadCount > 0"
        class="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white leading-none">
        {{ store.unreadCount > 9 ? '9+' : store.unreadCount }}
      </span>
    </button>

    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0 scale-95 -translate-y-1"
      enter-to-class="opacity-100 scale-100 translate-y-0"
      leave-active-class="transition duration-100 ease-in"
      leave-from-class="opacity-100 scale-100 translate-y-0"
      leave-to-class="opacity-0 scale-95 -translate-y-1">
      <div v-if="open"
        class="absolute right-0 mt-1 w-80 bg-white rounded-xl shadow-lg border border-gray-200 z-50 overflow-hidden">
        <div class="flex items-center justify-between px-4 py-2.5 border-b border-gray-100">
          <span class="text-sm font-semibold text-gray-700">通知</span>
          <button v-if="store.history.length" @click="store.markAllRead()"
            class="text-xs text-primary-600 hover:text-primary-700 bg-transparent transition-colors">
            全部已讀
          </button>
        </div>

        <div class="max-h-80 overflow-y-auto divide-y divide-gray-50">
          <div v-if="!store.history.length" class="px-4 py-6 text-center text-sm text-gray-400">
            目前沒有通知
          </div>
          <button v-for="n in store.history" :key="n.id"
            @click="store.markRead(n.id)"
            class="w-full text-left px-4 py-3 flex items-start gap-3 hover:bg-gray-50 transition-colors bg-transparent"
            :class="!n.read ? 'bg-primary-50/40' : ''">
            <span class="mt-0.5 text-base leading-none shrink-0" :class="iconColor[n.type]">
              {{ iconMap[n.type] }}
            </span>
            <div class="flex-1 min-w-0">
              <p class="text-sm text-gray-700 leading-snug" :class="!n.read ? 'font-medium' : ''">
                {{ n.message }}
              </p>
              <p class="text-xs text-gray-400 mt-0.5">{{ formatTime(n.at) }}</p>
            </div>
            <span v-if="!n.read" class="mt-1.5 h-2 w-2 rounded-full bg-primary-500 shrink-0" />
          </button>
        </div>

        <div v-if="store.history.length" class="px-4 py-2 border-t border-gray-100 text-center">
          <button @click="store.clear()"
            class="text-xs text-gray-400 hover:text-red-500 bg-transparent transition-colors">
            清除所有通知
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useNotificationStore } from '@/stores/notifications'

const store = useNotificationStore()
const open = ref(false)
const rootEl = ref(null)

const iconMap = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' }
const iconColor = {
  success: 'text-green-600',
  error: 'text-red-500',
  warning: 'text-yellow-500',
  info: 'text-blue-500',
}

function toggle() {
  open.value = !open.value
  if (open.value) store.markAllRead()
}

function handleClickOutside(e) {
  if (open.value && rootEl.value && !rootEl.value.contains(e.target)) {
    open.value = false
  }
}

function formatTime(ts) {
  const diff = Date.now() - ts
  if (diff < 60000) return '剛剛'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分鐘前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小時前`
  const d = new Date(ts)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

onMounted(() => document.addEventListener('click', handleClickOutside, true))
onUnmounted(() => document.removeEventListener('click', handleClickOutside, true))
</script>
