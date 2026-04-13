<template>
  <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-5
              hover:shadow-md transition-all cursor-pointer"
       @click="$emit('select', tutor.tutor_id)">
    <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
      <div>
        <h3 class="text-lg font-semibold text-gray-900">{{ tutor.display_name }}</h3>
        <p v-if="tutor.university" class="text-sm text-gray-500 mt-0.5">
          {{ tutor.university }}{{ tutor.department ? ' · ' + tutor.department : '' }}
        </p>
      </div>
      <div class="sm:text-right">
        <div class="text-lg font-bold" :class="hasRate ? 'text-primary-600' : 'text-gray-400'">
          <template v-if="hasRate">${{ tutor.subjects[0].hourly_rate }}/hr</template>
          <template v-else>費率未公開</template>
        </div>
        <div class="flex items-center gap-1 text-sm text-amber-500">
          <span>★</span>
          <span>{{ tutor.avg_rating || '-' }}</span>
          <span v-if="tutor.review_count" class="text-gray-400">({{ tutor.review_count }})</span>
        </div>
      </div>
    </div>
    <p v-if="tutor.self_intro" class="text-sm text-gray-600 mt-3 line-clamp-2">{{ tutor.self_intro }}</p>
    <div v-if="tutor.subjects && tutor.subjects.length" class="flex flex-wrap gap-2 mt-3">
      <span v-for="s in tutor.subjects" :key="s.subject_id"
            class="px-2 py-0.5 bg-primary-50 text-primary-700 text-xs rounded-full font-medium">
        {{ s.subject_name }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  tutor: {
    type: Object,
    required: true,
    // Surface shape mismatches during dev (e.g. API renames) before they
    // manifest as "$1.hourly_rate is undefined" deep in the template.
    validator: (t) => {
      if (t == null || typeof t !== 'object') return false
      if (t.tutor_id == null) return false
      if (typeof t.display_name !== 'string') return false
      if (t.subjects != null && !Array.isArray(t.subjects)) return false
      return true
    },
  },
})

defineEmits(['select'])

const hasRate = computed(() => {
  const first = props.tutor?.subjects?.[0]
  return first != null && first.hourly_rate != null
})
</script>
