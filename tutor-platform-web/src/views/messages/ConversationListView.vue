<template>
  <div>
    <PageHeader title="對話列表" />

    <div v-if="loading" class="text-center py-8 text-gray-500">載入中...</div>

    <div v-else-if="conversations.length" class="space-y-2">
      <div v-for="c in conversations" :key="c.conversation_id"
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
        </div>
        <span v-if="c.last_message_at" class="text-xs text-gray-400 shrink-0">
          {{ formatDate(c.last_message_at) }}
        </span>
      </div>
    </div>

    <p v-else-if="error" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ error }}</p>
    <EmptyState v-else message="尚無對話" />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { messagesApi } from '@/api/messages'
import PageHeader from '@/components/common/PageHeader.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const conversations = ref([])
const loading = ref(false)
const error = ref('')

function formatDate(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return d.toLocaleDateString('zh-TW') + ' ' + d.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })
}

let pollTimer = null

async function fetchConversations() {
  // Bug #22: 重抓前清除上次的錯誤，避免使用者看到過時訊息
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
  // 每 30 秒自動刷新對話列表
  pollTimer = setInterval(fetchConversations, 30000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>
