<template>
  <div>
    <PageHeader title="搜尋老師" />

    <TutorFilter :subjects="subjects" @search="doSearch" />

    <!-- Results -->
    <div v-if="loading" class="text-center py-8 text-gray-500">搜尋中...</div>

    <div v-else-if="tutors.length" class="grid gap-4 md:grid-cols-2">
      <TutorCard v-for="t in tutors" :key="t.tutor_id" :tutor="t"
                 @select="id => $router.push('/parent/tutor/' + id)" />
    </div>

    <EmptyState v-else message="沒有符合條件的老師" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { tutorsApi } from '@/api/tutors'
import { subjectsApi } from '@/api/subjects'
import PageHeader from '@/components/common/PageHeader.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import TutorFilter from '@/components/tutor/TutorFilter.vue'
import TutorCard from '@/components/tutor/TutorCard.vue'

const tutors = ref([])
const subjects = ref([])
const loading = ref(false)

async function doSearch(filters = {}) {
  loading.value = true
  try {
    const params = {}
    if (filters.subject_id) params.subject_id = filters.subject_id
    if (filters.min_rate) params.min_rate = filters.min_rate
    if (filters.max_rate) params.max_rate = filters.max_rate
    if (filters.school) params.school = filters.school
    params.sort_by = filters.sort_by || 'rating'
    tutors.value = await tutorsApi.search(params)
  } catch (e) {
    console.error(e.message)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    subjects.value = await subjectsApi.list()
  } catch (e) {
    console.error(e.message)
  }
  await doSearch()
})
</script>
