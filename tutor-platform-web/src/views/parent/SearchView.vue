<template>
  <div>
    <PageHeader title="搜尋老師" />

    <TutorFilter :subjects="subjects" @search="doSearch" />

    <!-- Results -->
    <div v-if="loading" class="animate-pulse grid gap-4 md:grid-cols-2">
      <div v-for="n in 4" :key="n" class="bg-white rounded-xl border border-gray-100 p-5">
        <div class="h-5 bg-gray-200 rounded w-1/3 mb-3"></div>
        <div class="h-4 bg-gray-200 rounded w-2/3 mb-2"></div>
        <div class="h-4 bg-gray-200 rounded w-1/2"></div>
      </div>
    </div>

    <div v-else-if="tutors.length" class="grid gap-4 md:grid-cols-2">
      <TutorCard v-for="t in tutors" :key="t.tutor_id" :tutor="t"
                 @select="id => $router.push('/parent/tutor/' + id)" />
    </div>

    <EmptyState v-else message="沒有符合條件的老師" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useToastStore } from '@/stores/toast'
import { tutorsApi } from '@/api/tutors'
import { subjectsApi } from '@/api/subjects'
import PageHeader from '@/components/common/PageHeader.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import TutorFilter from '@/components/tutor/TutorFilter.vue'
import TutorCard from '@/components/tutor/TutorCard.vue'

const toast = useToastStore()
const tutors = ref([])
const subjects = ref([])
const loading = ref(false)

async function doSearch(filters = {}) {
  loading.value = true
  try {
    const params = {}
    // Bug #20: 用 != null 檢查取代 falsy，避免使用者把費率設為 0 時被當成「未填」
    if (filters.subject_id != null && filters.subject_id !== '') params.subject_id = filters.subject_id
    if (filters.min_rate != null && filters.min_rate !== '') params.min_rate = filters.min_rate
    if (filters.max_rate != null && filters.max_rate !== '') params.max_rate = filters.max_rate
    if (filters.school) params.school = filters.school
    params.sort_by = filters.sort_by || 'rating'
    const res = await tutorsApi.search(params)
    tutors.value = res.items || []
  } catch (e) {
    toast.error('搜尋失敗：' + e.message)
  } finally {
    loading.value = false
  }
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
