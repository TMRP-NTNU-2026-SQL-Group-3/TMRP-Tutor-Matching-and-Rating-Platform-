import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const STORAGE_KEY = 'notifications'
const MAX_HISTORY = 50

let _savedHistory = []
try { _savedHistory = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]') } catch { /* corrupted */ }

// Seed the counter above any IDs already stored so new entries are always unique.
let _id = _savedHistory.reduce((max, n) => Math.max(max, typeof n.id === 'number' ? n.id : 0), 0)

export const useNotificationStore = defineStore('notifications', () => {
  const history = ref(_savedHistory)

  const unreadCount = computed(() => history.value.filter(n => !n.read).length)

  function add(type, message) {
    const now = Date.now()
    const entry = { id: ++_id, type, message, read: false, at: now }
    history.value = [entry, ...history.value].slice(0, MAX_HISTORY)
    _persist()
  }

  function markRead(id) {
    const n = history.value.find(n => n.id === id)
    if (n && !n.read) { n.read = true; _persist() }
  }

  function markAllRead() {
    let changed = false
    history.value.forEach(n => { if (!n.read) { n.read = true; changed = true } })
    if (changed) _persist()
  }

  function clear() {
    history.value = []
    _persist()
  }

  function _persist() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(history.value))
  }

  return { history, unreadCount, add, markRead, markAllRead, clear }
})
