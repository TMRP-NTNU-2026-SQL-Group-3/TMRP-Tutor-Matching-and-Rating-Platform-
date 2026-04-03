<template>
  <div class="text-center py-12">
    <div class="text-4xl mb-3 text-gray-300">
      <slot name="icon">{{ icon }}</slot>
    </div>
    <p class="text-gray-500">{{ message }}</p>
  </div>
</template>

<script setup>
defineProps({
  icon: { type: String, default: '---' },
  message: { type: String, required: true },
})
</script>
