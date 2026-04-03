<template>
  <div class="rounded-xl shadow-sm p-6 text-center" :class="highlight ? 'bg-primary-50 border border-primary-200' : 'bg-white border border-gray-100'">
    <p class="text-sm font-medium text-gray-500">{{ title }}</p>
    <p class="text-3xl font-bold mt-2" :class="highlight ? 'text-primary-700' : 'text-gray-900'">
      <slot>{{ value }}</slot>
    </p>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  value: { type: [String, Number], default: '' },
  highlight: { type: Boolean, default: false },
})
</script>
