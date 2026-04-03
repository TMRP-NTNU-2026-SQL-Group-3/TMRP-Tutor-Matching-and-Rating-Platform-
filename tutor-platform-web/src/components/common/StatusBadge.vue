<template>
  <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium" :class="classes">
    {{ label }}
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, required: true },
  label: { type: String, default: '' },
})

const statusMap = {
  pending:     'bg-amber-100 text-amber-700',
  trial:       'bg-blue-100 text-blue-700',
  active:      'bg-green-100 text-green-700',
  paused:      'bg-gray-100 text-gray-600',
  terminating: 'bg-purple-100 text-purple-700',
  ended:       'bg-red-100 text-red-700',
  rejected:    'bg-red-100 text-red-700',
  cancelled:   'bg-gray-100 text-gray-500',
}

const classes = computed(() => statusMap[props.status] || 'bg-gray-100 text-gray-600')
</script>
