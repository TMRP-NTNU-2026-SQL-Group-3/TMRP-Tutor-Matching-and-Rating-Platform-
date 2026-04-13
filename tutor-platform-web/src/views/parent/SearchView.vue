<template>
  <div>
    <PageHeader title="搜尋老師" />

    <TutorFilter :subjects="subjects" @search="onFiltersChanged" />

    <!-- Results -->
    <div v-if="loading" class="animate-pulse grid gap-4 md:grid-cols-2"
         role="status" aria-live="polite" aria-label="載入老師列表中">
      <div v-for="n in 4" :key="n" class="bg-white rounded-xl border border-gray-100 p-5">
        <div class="h-5 bg-gray-200 rounded w-1/3 mb-3"></div>
        <div class="h-4 bg-gray-200 rounded w-2/3 mb-2"></div>
        <div class="h-4 bg-gray-200 rounded w-1/2"></div>
      </div>
      <span class="sr-only">載入中...</span>
    </div>

    <template v-else-if="tutors.length">
      <div class="flex items-center justify-between mb-3 text-sm text-gray-500">
        <span>共 {{ total }} 位老師</span>
        <span>第 {{ page }} / {{ totalPages }} 頁</span>
      </div>
      <div class="grid gap-4 md:grid-cols-2">
        <TutorCard v-for="t in tutors" :key="t.tutor_id" :tutor="t"
                   @select="id => $router.push('/parent/tutor/' + id)" />
      </div>

      <!-- Pagination -->
      <nav v-if="totalPages > 1" aria-label="搜尋結果分頁"
        class="mt-6 flex items-center justify-center gap-2">
        <button @click="goToPage(page - 1)" :disabled="page <= 1"
          class="px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-sm text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
          上一頁
        </button>
        <button v-for="p in pageNumbers" :key="p.key" @click="p.num && goToPage(p.num)"
          :disabled="!p.num"
          :aria-current="p.num === page ? 'page' : null"
          :aria-label="p.num ? `第 ${p.num} 頁` : '省略頁碼'"
          :aria-hidden="!p.num ? 'true' : null"
          :tabindex="!p.num ? -1 : null"
          :class="[
            'min-w-[2.25rem] px-3 py-1.5 rounded-lg border text-sm transition-colors',
            !p.num
              ? 'border-transparent text-gray-400 cursor-default'
              : p.num === page
                ? 'border-primary-600 bg-primary-600 text-white'
                : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50',
          ]">
          {{ p.label }}
        </button>
        <button @click="goToPage(page + 1)" :disabled="page >= totalPages"
          class="px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-sm text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
          下一頁
        </button>
      </nav>
    </template>

    <EmptyState v-else message="沒有符合條件的老師" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useToastStore } from '@/stores/toast'
import { tutorsApi } from '@/api/tutors'
import { subjectsApi } from '@/api/subjects'
import PageHeader from '@/components/common/PageHeader.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import TutorFilter from '@/components/tutor/TutorFilter.vue'
import TutorCard from '@/components/tutor/TutorCard.vue'
import { PAGE_SIZE } from '@/constants'

const toast = useToastStore()
const tutors = ref([])
const subjects = ref([])
const loading = ref(false)
const page = ref(1)
const total = ref(0)
const lastFilters = ref({})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

// Build a compact pagination row: first, neighbors, last, with ellipsis gaps.
const pageNumbers = computed(() => {
  const tp = totalPages.value
  const cur = page.value
  if (tp <= 7) {
    return Array.from({ length: tp }, (_, i) => ({ key: `p${i + 1}`, num: i + 1, label: String(i + 1) }))
  }
  const result = []
  const push = (num) => result.push({ key: `p${num}`, num, label: String(num) })
  const gap = (key) => result.push({ key, num: null, label: '…' })
  push(1)
  const start = Math.max(2, cur - 1)
  const end = Math.min(tp - 1, cur + 1)
  if (start > 2) gap('g1')
  for (let i = start; i <= end; i++) push(i)
  if (end < tp - 1) gap('g2')
  push(tp)
  return result
})

async function doSearch(filters = {}, targetPage = 1) {
  loading.value = true
  try {
    const params = {}
    // Bug #20: Compare against null explicitly so a user-entered 0 isn't dropped as falsy.
    if (filters.subject_id != null && filters.subject_id !== '') params.subject_id = filters.subject_id
    if (filters.min_rate != null && filters.min_rate !== '') params.min_rate = filters.min_rate
    if (filters.max_rate != null && filters.max_rate !== '') params.max_rate = filters.max_rate
    if (filters.min_rating != null && filters.min_rating !== '') params.min_rating = filters.min_rating
    if (filters.school) params.school = filters.school
    params.sort_by = filters.sort_by || 'rating'
    params.page = targetPage
    params.page_size = PAGE_SIZE
    const res = await tutorsApi.search(params)
    tutors.value = res.items || []
    total.value = Number(res.total ?? 0)
    page.value = targetPage
  } catch (e) {
    toast.error('搜尋失敗：' + e.message)
  } finally {
    loading.value = false
  }
}

function onFiltersChanged(filters = {}) {
  lastFilters.value = { ...filters }
  doSearch(filters, 1)
}

function goToPage(num) {
  if (num < 1 || num > totalPages.value || num === page.value) return
  doSearch(lastFilters.value, num)
  if (typeof window !== 'undefined') window.scrollTo({ top: 0, behavior: 'smooth' })
}

onMounted(async () => {
  try {
    subjects.value = await subjectsApi.list()
  } catch (e) {
    toast.error('載入科目失敗')
  }
  await doSearch()
})
</script>
