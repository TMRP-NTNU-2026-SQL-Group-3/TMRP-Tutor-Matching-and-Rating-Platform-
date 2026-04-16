<template>
  <div class="flex flex-col h-[calc(100dvh_-_var(--nav-height,3.5rem)_-_var(--main-py,1.5rem)_*_2)] min-h-[60vh]">
    <PageHeader title="聊天" show-back />

    <div v-if="loading" class="flex-1 bg-gray-50 rounded-xl p-4 animate-pulse space-y-3"
         role="status" aria-live="polite" aria-label="載入訊息中">
      <div v-for="n in 5" :key="n" :class="n % 2 === 0 ? 'flex justify-end' : 'flex justify-start'">
        <div class="bg-gray-200 rounded-2xl h-10 w-48"></div>
      </div>
      <span class="sr-only">載入中...</span>
    </div>

    <template v-else>
      <!-- Messages area -->
      <div ref="chatContainer"
           class="flex-1 bg-gray-50 rounded-xl p-4 overflow-y-auto space-y-3 min-h-0">
        <div v-if="!messages.length" class="text-center text-gray-400 py-12">
          尚無訊息，開始對話吧！
        </div>
        <div v-for="msg in messages" :key="msg.message_id"
             :class="msg.sender_user_id === userId ? 'flex justify-end' : 'flex justify-start'">
          <div :class="[
            'max-w-[85%] sm:max-w-[70%] px-4 py-2',
            msg.sender_user_id === userId
              ? 'bg-primary-500 text-white rounded-2xl rounded-br-sm'
              : 'bg-white border border-gray-200 text-gray-800 rounded-2xl rounded-bl-sm'
          ]">
            <div :class="[
              'text-[11px] mb-0.5',
              msg.sender_user_id === userId ? 'text-primary-100' : 'text-gray-400'
            ]">
              {{ msg.sender_name }}
            </div>
            <div class="text-sm">{{ msg.content }}</div>
            <div :class="[
              'text-[10px] mt-1',
              msg.sender_user_id === userId ? 'text-primary-200' : 'text-gray-300'
            ]">
              {{ formatTime(msg.sent_at) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Input area -->
      <div class="sticky bottom-0 bg-white border-t border-gray-200 p-3 flex gap-2 mt-2 rounded-b-xl">
        <input v-model="newMessage" type="text" placeholder="輸入訊息..."
               class="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition"
               @keyup.enter="handleSend" />
        <button @click="handleSend" :disabled="sending || !newMessage.trim()"
          class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed shrink-0">
          {{ sending ? '...' : '傳送' }}
        </button>
      </div>

      <p v-if="error" role="alert" class="text-sm text-danger bg-red-50 rounded-lg p-3 mt-2">{{ error }}</p>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { messagesApi } from '@/api/messages'
import PageHeader from '@/components/common/PageHeader.vue'

const route = useRoute()
const auth = useAuthStore()

const messages = ref([])
const newMessage = ref('')
const loading = ref(false)
const sending = ref(false)
const error = ref('')
const chatContainer = ref(null)
const toast = useToastStore()
let pollTimer = null
// Bug #21: 用 fetchId 區分當前對話與舊對話，避免快速切換時舊請求覆蓋新資料
let fetchId = 0
// Bug #21: 紀錄當前 in-flight 的 fetch promise；新呼叫可 await 它以等待既有結果，
// 並於需要時再觸發新 fetch（例如送出訊息後一定要看到最新訊息）。
let inFlightFetch = null

const userId = computed(() => auth.user?.user_id)

function formatTime(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return d.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })
}

function scrollToBottom() {
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  })
}

// dedupe=true（預設，輪詢用）：若已有 in-flight fetch 則複用其 promise，避免重疊請求
// dedupe=false（送訊息後用）：等待既有 fetch 結束，再起一輪新的，確保看到最新訊息
async function fetchMessages({ dedupe = true } = {}) {
  if (inFlightFetch) {
    const existing = inFlightFetch
    if (dedupe) return existing
    try { await existing } catch { /* 既有 fetch 的錯誤由它自己處理 */ }
  }
  const myFetchId = fetchId
  const promise = (async () => {
    try {
      const result = await messagesApi.getMessages(route.params.id)
      if (myFetchId !== fetchId) return  // 對話已切換，丟棄舊結果
      // Preserve optimistic (pending) entries so a poll firing mid-send does not
      // visually drop the user's just-typed bubble.
      const pending = messages.value.filter(m => m.pending)
      messages.value = [...result, ...pending]
      scrollToBottom()
    } catch (e) {
      if (myFetchId === fetchId) error.value = e.message
    }
  })()
  inFlightFetch = promise
  try {
    await promise
  } finally {
    if (inFlightFetch === promise) inFlightFetch = null
  }
}

async function handleSend() {
  const text = newMessage.value.trim()
  if (!text) return
  error.value = ''
  sending.value = true
  // Optimistic append so the bubble shows up immediately and stays in the user's
  // intended order even when send takes 1–3s. The temp entry is wiped by the
  // refetch that runs after the server confirms.
  const tempId = `tmp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  const tempMessage = {
    message_id: tempId,
    sender_user_id: userId.value,
    sender_name: auth.user?.display_name || '我',
    content: text,
    sent_at: new Date().toISOString(),
    pending: true,
  }
  messages.value = [...messages.value, tempMessage]
  newMessage.value = ''
  scrollToBottom()
  try {
    await messagesApi.sendMessage(route.params.id, text)
    // 送出後強制一輪新 fetch，避免落入既有 in-flight poll 的舊快照；
    // refetch 會以伺服器版本（含真正的 message_id）覆蓋 messages，移除 temp。
    await fetchMessages({ dedupe: false })
  } catch (e) {
    // Roll back the optimistic entry so the user can retry without a phantom.
    messages.value = messages.value.filter(m => m.message_id !== tempId)
    newMessage.value = text
    error.value = e.message
    toast.error('訊息傳送失敗')
  } finally {
    sending.value = false
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(() => {
    if (typeof document !== 'undefined' && document.hidden) return
    if (typeof navigator !== 'undefined' && !navigator.onLine) return
    fetchMessages()
  }, 5000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// Bug #21: 切換回分頁時立即拉一次最新訊息，補齊隱藏期間的更新
function onVisibilityChange() {
  if (typeof document !== 'undefined' && !document.hidden) {
    fetchMessages()
  }
}

watch(() => route.params.id, async () => {
  fetchId++  // 標記新對話開始；舊請求的回應將被丟棄
  loading.value = true
  error.value = ''
  messages.value = []
  // dedupe:false — 若恰好有舊對話的 poll 仍 in-flight，等它結束後再起一輪新的，
  // 否則新對話將拿不到資料（舊 promise 的結果被 fetchId 過濾掉了）
  await fetchMessages({ dedupe: false })
  loading.value = false
  startPolling()
}, { immediate: true })

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', onVisibilityChange)
}

onUnmounted(() => {
  stopPolling()
  // F-05: detach the visibility listener BEFORE bumping fetchId. If we bumped
  // first, a visibilitychange firing in this tiny window would call
  // fetchMessages() with the new fetchId, so its result would pass the
  // currentFetchId === fetchId guard and overwrite messages on a dead component.
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', onVisibilityChange)
  }
  fetchId++  // discard any in-flight responses started before unmount
})
</script>
