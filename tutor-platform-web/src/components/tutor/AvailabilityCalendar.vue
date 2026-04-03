<template>
  <div v-if="slots && slots.length" class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
    <h3 class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">可授課時段</h3>
    <div class="space-y-1.5">
      <div v-for="a in slots" :key="a.availability_id"
           class="flex items-center justify-between text-sm py-1">
        <span class="font-medium text-gray-700">{{ dayNames[a.day_of_week] || '第' + a.day_of_week + '天' }}</span>
        <span class="text-gray-500">{{ formatTime(a.start_time) }} - {{ formatTime(a.end_time) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  slots: { type: Array, default: () => [] },
})

const dayNames = { 0: '週日', 1: '週一', 2: '週二', 3: '週三', 4: '週四', 5: '週五', 6: '週六' }

function formatTime(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  return d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0')
}
</script>
