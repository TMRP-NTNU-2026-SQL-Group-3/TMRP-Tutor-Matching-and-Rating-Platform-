<template>
  <div>
    <div v-if="loading" class="text-center py-8 text-gray-500">載入中...</div>

    <div v-else-if="tutor">
      <!-- Hero section -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-6">
        <div class="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
          <div>
            <h1 class="text-2xl font-bold text-gray-900">{{ tutor.display_name }}</h1>
            <p v-if="tutor.university || tutor.department" class="text-gray-500 mt-1">
              <span v-if="tutor.university">{{ tutor.university }}</span>
              <span v-if="tutor.department"> — {{ tutor.department }}</span>
              <span v-if="tutor.grade_year"> {{ tutor.grade_year }} 年級</span>
            </p>
          </div>
          <div class="flex items-center gap-4 text-sm">
            <div v-if="tutor.rating && tutor.rating.review_count" class="text-center">
              <div class="text-2xl font-bold text-amber-500">{{ avgRating }}</div>
              <div class="text-gray-400">{{ tutor.rating.review_count }} 則評價</div>
            </div>
            <div class="text-center">
              <div class="text-2xl font-bold text-gray-900">{{ tutor.active_student_count || 0 }}</div>
              <div class="text-gray-400">/ {{ tutor.max_students || 5 }} 學生</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Rating radar chart -->
      <RadarChart
        v-if="tutor.rating && tutor.rating.review_count"
        :values="[tutor.rating.avg_r1 || 0, tutor.rating.avg_r2 || 0, tutor.rating.avg_r3 || 0, tutor.rating.avg_r4 || 0]"
        :review-count="tutor.rating.review_count"
        class="mb-6"
      />

      <!-- Info grid -->
      <div class="grid md:grid-cols-2 gap-6 mb-6">
        <!-- Left: intro + experience -->
        <div class="space-y-6">
          <div v-if="tutor.self_intro" class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
            <h3 class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">自我介紹</h3>
            <p class="text-gray-700 whitespace-pre-line">{{ tutor.self_intro }}</p>
          </div>
          <div v-if="tutor.teaching_experience" class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
            <h3 class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">教學經驗</h3>
            <p class="text-gray-700 whitespace-pre-line">{{ tutor.teaching_experience }}</p>
          </div>
        </div>

        <!-- Right: subjects + availability -->
        <div class="space-y-6">
          <div v-if="tutor.subjects && tutor.subjects.length" class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
            <h3 class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">授課科目</h3>
            <div class="space-y-2">
              <div v-for="s in tutor.subjects" :key="s.subject_id"
                   class="flex items-center justify-between py-1.5">
                <span class="px-2.5 py-0.5 bg-primary-50 text-primary-700 text-sm rounded-full font-medium">
                  {{ s.subject_name }}
                </span>
                <span v-if="s.hourly_rate" class="text-sm font-semibold text-gray-700">${{ s.hourly_rate }}/hr</span>
              </div>
            </div>
          </div>
          <AvailabilityCalendar :slots="tutor.availability" />
        </div>
      </div>

      <!-- Actions -->
      <div class="flex gap-3 mb-6">
        <button @click="goMessage"
          class="bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 rounded-lg px-4 py-2 text-sm font-medium transition-colors">
          發送訊息
        </button>
        <button v-if="!showInviteForm" @click="showInviteForm = true"
          class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors">
          發送媒合邀請
        </button>
      </div>

      <!-- Invite form -->
      <InviteForm
        :visible="showInviteForm"
        :students="students"
        :subjects="tutor.subjects || []"
        :submitting="inviting"
        :error="inviteError"
        @submit="submitInvite"
        @cancel="showInviteForm = false"
      />
    </div>

    <EmptyState v-else message="找不到此老師" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { tutorsApi } from '@/api/tutors'
import { studentsApi } from '@/api/students'
import { matchesApi } from '@/api/matches'
import { messagesApi } from '@/api/messages'
import EmptyState from '@/components/common/EmptyState.vue'
import RadarChart from '@/components/review/RadarChart.vue'
import AvailabilityCalendar from '@/components/tutor/AvailabilityCalendar.vue'
import InviteForm from '@/components/match/InviteForm.vue'

const route = useRoute()
const router = useRouter()

const tutor = ref(null)
const students = ref([])
const loading = ref(false)
const showInviteForm = ref(false)
const inviting = ref(false)
const inviteError = ref('')


const avgRating = computed(() => {
  if (!tutor.value?.rating) return 0
  const r = tutor.value.rating
  const vals = [r.avg_r1, r.avg_r2, r.avg_r3, r.avg_r4].filter(v => v != null)
  if (!vals.length) return 0
  return (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1)
})

async function goMessage() {
  try {
    const conv = await messagesApi.createConversation(tutor.value.user_id)
    router.push('/messages/' + conv.conversation_id)
  } catch (e) {
    alert(e.message)
  }
}

async function submitInvite(formData) {
  inviteError.value = ''
  if (!formData.student_id || !formData.subject_id) {
    inviteError.value = '請選擇子女和科目'
    return
  }
  inviting.value = true
  try {
    await matchesApi.create({
      tutor_id: tutor.value.tutor_id,
      ...formData,
      invite_message: formData.invite_message || null,
    })
    alert('邀請已送出！')
    showInviteForm.value = false
  } catch (e) {
    inviteError.value = e.message
  } finally {
    inviting.value = false
  }
}

onMounted(async () => {
  loading.value = true
  try {
    const id = route.params.id
    tutor.value = await tutorsApi.getDetail(id)
    students.value = await studentsApi.list()
  } catch (e) {
    console.error(e.message)
  } finally {
    loading.value = false
  }
})
</script>
