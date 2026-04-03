<template>
  <div class="flex flex-col" style="height: calc(100vh - 120px);">
    <PageHeader title="聊天" />

    <div v-if="loading" class="text-center py-8 text-gray-500 flex-1">載入中...</div>

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
            'max-w-[70%] px-4 py-2',
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

      <p v-if="error" class="text-sm text-danger bg-red-50 rounded-lg p-3 mt-2">{{ error }}</p>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
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
let pollTimer = null

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

async function fetchMessages() {
  try {
    messages.value = await messagesApi.getMessages(route.params.id)
    scrollToBottom()
  } catch (e) {
    error.value = e.message
  }
}

async function handleSend() {
  if (!newMessage.value.trim()) return
  error.value = ''
  sending.value = true
  try {
    await messagesApi.sendMessage(route.params.id, newMessage.value.trim())
    newMessage.value = ''
    await fetchMessages()
  } catch (e) {
    error.value = e.message
  } finally {
    sending.value = false
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(fetchMessages, 5000)
}

onMounted(async () => {
  loading.value = true
  await fetchMessages()
  loading.value = false
  startPolling()
})

watch(() => route.params.id, async () => {
  loading.value = true
  error.value = ''
  messages.value = []
  await fetchMessages()
  loading.value = false
  startPolling()
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>
