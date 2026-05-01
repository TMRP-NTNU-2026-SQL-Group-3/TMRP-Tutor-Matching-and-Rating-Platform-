import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const MAX_HISTORY = 50
// FE-5: discard notifications older than 1 hour on init so a shared-device
// user cannot read the previous session's notification history via devtools.
const MAX_AGE_MS = 60 * 60 * 1000

// FE-5: scope the storage key to the authenticated user so notifications from
// one session are never visible to the next user on the same device.
function storageKey() {
  try {
    const u = JSON.parse(localStorage.getItem('user') || 'null')
    return u?.user_id ? `notifications_${u.user_id}` : 'notifications'
  } catch {
    return 'notifications'
  }
}

function loadHistory() {
  try {
    const raw = JSON.parse(localStorage.getItem(storageKey()) || '[]')
    const cutoff = Date.now() - MAX_AGE_MS
    return raw.filter(n => typeof n.at === 'number' && n.at >= cutoff)
  } catch {
    return []
  }
}

let _savedHistory = loadHistory()
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
    // FE-5: capture the key before auth.logout() removes localStorage.user,
    // since storageKey() reads the user record to build the scoped key.
    // Without this, clear() would write to the generic fallback key and leave
    // the user-scoped key populated until the 1-hour expiry.
    const key = storageKey()
    history.value = []
    localStorage.setItem(key, '[]')
  }

  function _persist() {
    // FE-5: never persist error-level entries — they may contain internal
    // system details (user IDs, match IDs) that must not outlive the session.
    const toSave = history.value.filter(n => n.type !== 'error')
    localStorage.setItem(storageKey(), JSON.stringify(toSave))
  }

  return { history, unreadCount, add, markRead, markAllRead, clear }
})
