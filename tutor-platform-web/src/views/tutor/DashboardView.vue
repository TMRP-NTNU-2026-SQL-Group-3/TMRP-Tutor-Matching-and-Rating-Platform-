<template>
  <div>
    <!-- Welcome -->
    <div class="bg-gradient-to-r from-primary-50 to-white rounded-xl p-6 mb-6">
      <h1 class="text-2xl font-bold text-gray-900">歡迎，{{ auth.user?.display_name }}</h1>
      <p class="text-gray-500 mt-1">管理您的教學配對</p>
    </div>

    <!-- Match list -->
    <h2 class="text-lg font-semibold text-gray-900 mb-3">我的配對</h2>

    <div v-if="loading" class="animate-pulse space-y-3"
         role="status" aria-live="polite" aria-label="載入配對列表中">
      <div v-for="n in 3" :key="n" class="bg-white rounded-lg border border-gray-100 p-4 flex items-center justify-between">
        <div>
          <div class="h-5 bg-gray-200 rounded w-24 mb-2"></div>
          <div class="h-4 bg-gray-200 rounded w-40"></div>
        </div>
        <div class="h-6 bg-gray-200 rounded-full w-16"></div>
      </div>
      <span class="sr-only">載入中...</span>
    </div>

    <div v-else-if="matches.length" class="space-y-3">
      <div v-for="m in matches" :key="m.match_id"
           class="bg-white rounded-lg shadow-sm border border-gray-100 p-4
                  hover:shadow-md transition-shadow cursor-pointer
                  flex items-center justify-between"
           @click="$router.push('/tutor/match/' + m.match_id)">
        <div>
          <p class="font-semibold text-gray-900">{{ m.student_name }}</p>
          <p class="text-sm text-gray-500">{{ m.subject_name }}</p>
        </div>
        <StatusBadge :status="m.status" :label="m.status_label" />
      </div>
    </div>

    <EmptyState v-else message="尚無配對紀錄" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { matchesApi } from '@/api/matches'
import StatusBadge from '@/components/common/StatusBadge.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const auth = useAuthStore()
const toast = useToastStore()
const matches = ref([])
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    matches.value = await matchesApi.list()
  } catch (e) {
    toast.error('載入配對資料失敗')
  } finally {
    loading.value = false
  }
})
</script>
