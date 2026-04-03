<template>
  <div v-if="sessions.length" class="border-l-2 border-primary-200 pl-4 space-y-4">
    <div v-for="s in sessions" :key="s.session_id">
      <div class="flex items-center gap-3 mb-1">
        <span class="px-2 py-0.5 bg-primary-50 text-primary-700 text-xs rounded-full font-medium">
          {{ formatDate(s.session_date) }}
        </span>
        <span class="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded-full">
          {{ s.hours }} 小時
        </span>
        <span v-if="showVisibility && (!s.visible_to_parent || s.visible_to_parent === 0)"
              class="px-2 py-0.5 bg-amber-100 text-amber-700 text-xs rounded-full">
          家長不可見
        </span>
      </div>
      <p class="text-sm text-gray-700"><span class="font-medium">內容：</span>{{ s.content_summary }}</p>
      <p v-if="s.homework" class="text-sm text-gray-600 bg-gray-50 rounded p-2 mt-1">
        <span class="font-medium">作業：</span>{{ s.homework }}
      </p>
      <p v-if="s.student_performance" class="text-sm text-gray-600 bg-gray-50 rounded p-2 mt-1">
        <span class="font-medium">表現：</span>{{ s.student_performance }}
      </p>
      <p v-if="s.next_plan" class="text-sm text-gray-600 bg-gray-50 rounded p-2 mt-1">
        <span class="font-medium">下次計畫：</span>{{ s.next_plan }}
      </p>
    </div>
  </div>
  <p v-else class="text-gray-400 text-sm">尚無上課紀錄</p>
</template>

<script setup>
defineProps({
  sessions: { type: Array, default: () => [] },
  showVisibility: { type: Boolean, default: false },
})

function formatDate(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleDateString('zh-TW')
}
</script>
