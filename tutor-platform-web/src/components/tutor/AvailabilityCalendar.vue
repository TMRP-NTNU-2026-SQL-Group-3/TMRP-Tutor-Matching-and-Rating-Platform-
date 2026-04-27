<template>
  <div v-if="slots && slots.length" class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
    <h3 class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">可授課時段</h3>
    <div class="space-y-2.5">
      <div v-for="day in orderedDays" :key="day" class="flex items-start gap-3">
        <span class="w-10 flex-shrink-0 text-sm font-medium text-gray-700 pt-0.5">
          {{ dayNames[day] }}
        </span>
        <div class="flex flex-wrap gap-1.5">
          <button
            v-for="slot in slotsByDay[day]"
            :key="slot.availability_id"
            type="button"
            @click="selectable ? handleSelect(slot) : undefined"
            :class="[
              'px-2.5 py-1 rounded-full text-xs font-medium border transition-colors',
              isSelected(slot)
                ? 'bg-primary-600 border-primary-600 text-white'
                : selectable
                  ? 'bg-gray-50 border-gray-200 text-gray-700 hover:bg-primary-50 hover:border-primary-300 hover:text-primary-700 cursor-pointer'
                  : 'bg-gray-50 border-gray-200 text-gray-700 cursor-default'
            ]"
          >
            {{ formatTime(slot.start_time) }}–{{ formatTime(slot.end_time) }}
          </button>
        </div>
      </div>
    </div>
    <p v-if="selectable && modelValue" class="mt-3 text-xs text-primary-600">
      已選：{{ dayNames[modelValue.day_of_week] }} {{ formatTime(modelValue.start_time) }}–{{ formatTime(modelValue.end_time) }}
    </p>
    <p v-else-if="selectable" class="mt-3 text-xs text-gray-400">
      點選時段以標記偏好時間
    </p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  slots: { type: Array, default: () => [] },
  selectable: { type: Boolean, default: false },
  modelValue: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue'])

const DAY_ORDER = [1, 2, 3, 4, 5, 6, 0]
const dayNames = { 0: '週日', 1: '週一', 2: '週二', 3: '週三', 4: '週四', 5: '週五', 6: '週六' }

const slotsByDay = computed(() => {
  const map = {}
  for (const slot of props.slots) {
    const d = slot.day_of_week
    if (!map[d]) map[d] = []
    map[d].push(slot)
  }
  for (const day of Object.keys(map)) {
    map[day].sort((a, b) => (a.start_time > b.start_time ? 1 : -1))
  }
  return map
})

const orderedDays = computed(() =>
  DAY_ORDER.filter(d => slotsByDay.value[d]?.length)
)

function isSelected(slot) {
  return props.modelValue?.availability_id === slot.availability_id
}

function handleSelect(slot) {
  emit('update:modelValue', isSelected(slot) ? null : slot)
}

function formatTime(dt) {
  if (!dt) return ''
  if (typeof dt === 'string' && /^\d{2}:\d{2}/.test(dt)) return dt.slice(0, 5)
  const d = new Date(dt)
  if (isNaN(d.getTime())) return dt
  return d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0')
}
</script>
