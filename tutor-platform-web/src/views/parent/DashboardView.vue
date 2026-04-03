<template>
  <div>
    <!-- Welcome -->
    <div class="bg-gradient-to-r from-primary-50 to-white rounded-xl p-6 mb-6">
      <h1 class="text-2xl font-bold text-gray-900">歡迎，{{ auth.user?.display_name }}</h1>
      <p class="text-gray-500 mt-1">管理您的家教配對</p>
    </div>

    <!-- Match list -->
    <h2 class="text-lg font-semibold text-gray-900 mb-3">我的配對</h2>

    <div v-if="loading" class="text-center py-8 text-gray-500">載入中...</div>

    <div v-else-if="matches.length" class="space-y-3">
      <div v-for="m in matches" :key="m.match_id"
           class="bg-white rounded-lg shadow-sm border border-gray-100 p-4
                  hover:shadow-md transition-shadow cursor-pointer
                  flex items-center justify-between"
           @click="$router.push('/parent/match/' + m.match_id)">
        <div>
          <p class="font-semibold text-gray-900">{{ m.tutor_display_name }}</p>
          <p class="text-sm text-gray-500">{{ m.subject_name }} · {{ m.student_name }}</p>
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
import { matchesApi } from '@/api/matches'
import StatusBadge from '@/components/common/StatusBadge.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const auth = useAuthStore()
const matches = ref([])
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    matches.value = await matchesApi.list()
  } catch (e) {
    console.error(e.message)
  } finally {
    loading.value = false
  }
})
</script>
