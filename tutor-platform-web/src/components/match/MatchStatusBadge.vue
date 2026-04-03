<template>
  <span :class="[baseClass, colorClass]">
    {{ label || statusLabels[status] || status }}
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, required: true },
  label: { type: String, default: '' },
})

const baseClass = 'px-2.5 py-0.5 text-xs font-semibold rounded-full'

const statusLabels = {
  pending: '待回覆',
  trial: '試教中',
  active: '進行中',
  paused: '已暫停',
  terminating: '終止中',
  ended: '已結束',
  cancelled: '已取消',
  rejected: '已拒絕',
}

const colorMap = {
  pending: 'bg-amber-100 text-amber-700',
  trial: 'bg-blue-100 text-blue-700',
  active: 'bg-green-100 text-green-700',
  paused: 'bg-gray-100 text-gray-600',
  terminating: 'bg-red-100 text-red-700',
  ended: 'bg-gray-200 text-gray-500',
  cancelled: 'bg-gray-200 text-gray-500',
  rejected: 'bg-red-100 text-red-600',
}

const colorClass = computed(() => colorMap[props.status] || 'bg-gray-100 text-gray-600')
</script>
