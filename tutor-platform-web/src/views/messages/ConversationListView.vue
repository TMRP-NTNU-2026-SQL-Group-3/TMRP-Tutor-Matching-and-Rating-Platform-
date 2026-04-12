<template>
  <div>
    <PageHeader title="對話列表" />

    <div v-if="!loading && conversations.length" class="mb-4">
      <label for="conv-search" class="sr-only">搜尋對話</label>
      <input id="conv-search" v-model="searchQuery" type="search" placeholder="搜尋對話對象..."
        class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
    </div>

    <div v-if="loading" class="text-center py-8 text-gray-500">載入中...</div>

    <div v-else-if="filteredConversations.length" class="space-y-2">
      <div v-for="c in filteredConversations" :key="c.conversation_id ?? `missing-${c.other_user_id}`"
           :class="[
             'bg-white rounded-lg shadow-sm border border-gray-100 p-4 transition-colors flex items-center gap-4',
             c.conversation_id != null
               ? 'hover:bg-gray-50 cursor-pointer'
               : 'opacity-60 cursor-not-allowed'
           ]"
           :title="c.conversation_id == null ? '對話資料不完整，無法開啟' : ''"
           @click="c.conversation_id != null && $router.push('/messages/' + c.conversation_id)">
        <!-- Avatar circle -->
        <div class="w-10 h-10 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center font-semibold text-sm shrink-0">
          {{ (c.other_name || '?').charAt(0) }}
        </div>
        <div class="flex-1 min-w-0">
          <p class="font-medium text-gray-900 truncate">{{ c.other_name }}</p>
          <p v-if="c.last_message_at" class="text-xs text-gray-400 mt-0.5">
            {{ formatRelative(c.last_message_at) }}
          </p>
          <p v-else class="text-xs text-gray-300 mt-0.5 italic">尚無訊息</p>
        </div>
        <span v-if="c.last_message_at" class="text-xs text-gray-400 shrink-0">
          {{ formatDate(c.last_message_at) }}
        </span>
      </div>
    </div>

    <p v-else-if="error" role="alert" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ error }}</p>
    <EmptyState v-else-if="!conversations.length" message="尚無對話" />
    <EmptyState v-else message="沒有符合的對話" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { messagesApi } from '@/api/messages'
import PageHeader from '@/components/common/PageHeader.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const conversations = ref([])
const loading = ref(false)
const error = ref('')
const searchQuery = ref('')

const filteredConversations = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return conversations.value
  return conversations.value.filter(c =>
    (c.other_name || '').toLowerCase().includes(q)
  )
})

function formatDate(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return d.toLocaleDateString('zh-TW') + ' ' + d.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })
}

function formatRelative(dt) {
  if (!dt) return ''
  const d = new Date(dt).getTime()
  const diffMs = Date.now() - d
  const min = Math.floor(diffMs / 60000)
  if (min < 1) return '剛剛'
  if (min < 60) return `${min} 分鐘前`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr} 小時前`
  const day = Math.floor(hr / 24)
  if (day < 7) return `${day} 天前`
  return new Date(dt).toLocaleDateString('zh-TW')
}

let pollTimer = null

async function fetchConversations() {
  // Bug #22: Clear previous error before refetching so users don't see stale messages.
  error.value = ''
  try {
    conversations.value = await messagesApi.listConversations()
  } catch (e) {
    error.value = e.message
  }
}

onMounted(async () => {
  loading.value = true
  await fetchConversations()
  loading.value = false
  // Auto refresh conversation list every 30 seconds.
  pollTimer = setInterval(fetchConversations, 30000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>
