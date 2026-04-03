<template>
  <div v-if="reviews.length" class="space-y-3">
    <div v-for="r in reviews" :key="r.review_id" class="bg-gray-50 rounded-lg p-4">
      <div class="flex items-center justify-between mb-2">
        <span class="font-medium text-gray-900">{{ r.reviewer_name }}</span>
        <span class="px-2 py-0.5 bg-gray-200 text-gray-600 text-xs rounded-full">{{ typeLabel(r.review_type) }}</span>
      </div>
      <div class="flex items-center gap-1 text-amber-500 text-sm mb-2">
        <span>★ {{ r.rating_1 }}</span>
        <span class="text-gray-300">/</span>
        <span>{{ r.rating_2 }}</span>
        <span class="text-gray-300">/</span>
        <span>{{ r.rating_3 || '-' }}</span>
        <span class="text-gray-300">/</span>
        <span>{{ r.rating_4 || '-' }}</span>
      </div>
      <p v-if="r.personality_comment" class="text-sm text-gray-600">{{ r.personality_comment }}</p>
      <p v-if="r.comment" class="text-sm text-gray-600 mt-1">{{ r.comment }}</p>
    </div>
  </div>
  <p v-else class="text-gray-400 text-sm">尚無評價</p>
</template>

<script setup>
defineProps({
  reviews: { type: Array, default: () => [] },
})

function typeLabel(type) {
  const map = { parent_to_tutor: '家長→老師', tutor_to_parent: '老師→家長', tutor_to_student: '老師→學生' }
  return map[type] || type
}
</script>
