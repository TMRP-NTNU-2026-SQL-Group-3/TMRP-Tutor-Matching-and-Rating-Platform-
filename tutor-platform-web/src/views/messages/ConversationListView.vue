<template>
  <div>
    <PageHeader title="對話列表" />

    <div v-if="!loading && conversations.length" class="mb-4 relative">
      <label for="conv-search" class="sr-only">搜尋對話</label>
      <input id="conv-search" v-model="searchQuery" type="search" placeholder="搜尋對話對象或訊息內容..."
        class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
      <span v-if="searching" class="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">搜尋中...</span>
    </div>
    <p v-if="searchFallback" role="status" class="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mt-2">
      伺服器搜尋暫時無法使用，目前僅顯示本機快取結果，部分對話可能未列出。
    </p>

    <div v-if="loading" class="text-center py-8 text-gray-500">載入中...</div>

    <div v-else-if="filteredConversations.length" class="space-y-2">
      <div v-for="c in pagedConversations" :key="c.conversation_id ?? `missing-${c.other_user_id}`"
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
          <p class="font-medium text-gray-900 truncate">
            <template v-if="searchQuery.trim()">
              <template v-for="(part, i) in highlightParts(c.other_name, searchQuery.trim())" :key="i">
                <mark v-if="part.mark" class="bg-yellow-100 text-gray-900 rounded-sm px-0.5">{{ part.text }}</mark><span v-else>{{ part.text }}</span>
              </template>
            </template>
            <template v-else>{{ c.other_name }}</template>
          </p>
          <p v-if="c.last_message_content" class="text-sm text-gray-600 truncate mt-0.5">
            <template v-if="searchQuery.trim()">
              <template v-for="(part, i) in highlightParts(formatPreview(c), searchQuery.trim())" :key="i">
                <mark v-if="part.mark" class="bg-yellow-100 text-gray-900 rounded-sm px-0.5">{{ part.text }}</mark><span v-else>{{ part.text }}</span>
              </template>
            </template>
            <template v-else>{{ formatPreview(c) }}</template>
          </p>
          <p v-else-if="c.last_message_at" class="text-xs text-gray-400 italic mt-0.5">已建立對話</p>
          <p v-else class="text-xs text-gray-300 mt-0.5 italic">尚無訊息</p>
        </div>
        <div v-if="c.last_message_at" class="flex flex-col items-end shrink-0 text-xs text-gray-400 gap-0.5">
          <span :title="formatDateTimeFull(c.last_message_at)">{{ formatRelative(c.last_message_at) }}</span>
          <span class="text-gray-300">{{ formatDateTimeShort(c.last_message_at) }}</span>
        </div>
      </div>
      <div v-if="filteredConversations.length > pagedConversations.length" class="mt-3 text-center">
        <button @click="displayPage++"
                class="text-sm text-primary-600 hover:text-primary-800 font-medium">
          載入更多（還有 {{ filteredConversations.length - pagedConversations.length }} 筆）
        </button>
      </div>
    </div>

    <p v-else-if="error && !conversations.length" role="alert" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ error }}</p>
    <EmptyState v-else-if="!conversations.length" message="尚無對話" />
    <EmptyState v-else message="沒有符合的對話" />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { messagesApi } from '@/api/messages'
import { useAuthStore } from '@/stores/auth'
import PageHeader from '@/components/common/PageHeader.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import { formatDateTimeShort, formatDateTimeFull } from '@/utils/format'
import { highlightParts } from '@/utils/highlight'

const auth = useAuthStore()
const conversations = ref([])
const loading = ref(false)
const error = ref('')
const searchQuery = ref('')
const serverSearchResults = ref(null)
const searching = ref(false)
const searchFallback = ref(false)
const displayPage = ref(1)

const PREVIEW_MAX = 50
const PAGE_SIZE = 20

let searchTimer = null
let searchSeq = 0
watch(searchQuery, (q) => {
  displayPage.value = 1
  if (searchTimer) clearTimeout(searchTimer)
  const trimmed = q.trim()
  if (!trimmed) {
    searchSeq++
    serverSearchResults.value = null
    searchFallback.value = false
    searching.value = false
    return
  }
  searching.value = true
  const seq = ++searchSeq
  searchTimer = setTimeout(async () => {
    try {
      const results = await messagesApi.search(trimmed)
      if (seq === searchSeq) {
        serverSearchResults.value = results
        searchFallback.value = false
      }
    } catch {
      if (seq === searchSeq) {
        serverSearchResults.value = null
        searchFallback.value = true
      }
    } finally {
      if (seq === searchSeq) searching.value = false
    }
  }, 300)
})

const filteredConversations = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return conversations.value
  // Use server-side results when available
  if (serverSearchResults.value) return serverSearchResults.value
  // Local fallback: search name and full last_message_content
  return conversations.value.filter(c =>
    (c.other_name || '').toLowerCase().includes(q)
    || (c.last_message_content || '').toLowerCase().includes(q)
  )
})

const pagedConversations = computed(() =>
  filteredConversations.value.slice(0, displayPage.value * PAGE_SIZE)
)

function formatPreview(c) {
  const raw = (c.last_message_content || '').trim()
  if (!raw) return ''
  const truncated = raw.length > PREVIEW_MAX ? raw.slice(0, PREVIEW_MAX) + '…' : raw
  const myId = auth.user?.user_id
  return c.last_message_sender_id === myId ? `我：${truncated}` : truncated
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
  if (searchTimer) clearTimeout(searchTimer)
})
</script>
