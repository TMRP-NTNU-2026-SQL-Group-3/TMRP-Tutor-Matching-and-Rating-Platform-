<template>
  <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-5 mb-6">
    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 items-end">
      <div class="flex flex-col gap-1">
        <label class="text-xs font-medium text-gray-500">科目</label>
        <select v-model="local.subject_id"
          class="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition">
          <option :value="null">全部</option>
          <option v-for="s in subjects" :key="s.subject_id" :value="s.subject_id">
            {{ s.subject_name }}
          </option>
        </select>
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs font-medium text-gray-500">最低時薪</label>
        <input v-model.number="local.min_rate" type="number" min="0" placeholder="不限"
          class="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs font-medium text-gray-500">最高時薪</label>
        <input v-model.number="local.max_rate" type="number" min="0" placeholder="不限"
          class="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs font-medium text-gray-500">學校</label>
        <input v-model="local.school" type="text" placeholder="關鍵字" @input="onSchoolInput"
          class="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
      </div>
      <div class="flex flex-col gap-1">
        <label class="text-xs font-medium text-gray-500">排序</label>
        <select v-model="local.sort_by"
          class="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition">
          <option value="rating">評分最高</option>
          <option value="rate_asc">時薪最低</option>
          <option value="newest">最新加入</option>
        </select>
      </div>
      <button @click="emitSearch"
        class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors">
        搜尋
      </button>
    </div>
  </div>
</template>

<script setup>
import { reactive, watch, onUnmounted } from 'vue'

const props = defineProps({
  subjects: { type: Array, default: () => [] },
  initial: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['search'])

const local = reactive({
  subject_id: props.initial.subject_id ?? null,
  min_rate: props.initial.min_rate ?? null,
  max_rate: props.initial.max_rate ?? null,
  school: props.initial.school ?? '',
  sort_by: props.initial.sort_by ?? 'rating',
})

watch(() => props.initial, (val) => {
  Object.assign(local, {
    subject_id: val.subject_id ?? null,
    min_rate: val.min_rate ?? null,
    max_rate: val.max_rate ?? null,
    school: val.school ?? '',
    sort_by: val.sort_by ?? 'rating',
  })
}, { deep: true })

let debounceTimer = null

function onSchoolInput() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    emitSearch()
  }, 300)
}

function emitSearch() {
  clearTimeout(debounceTimer)
  emit('search', { ...local })
}

onUnmounted(() => clearTimeout(debounceTimer))
</script>
