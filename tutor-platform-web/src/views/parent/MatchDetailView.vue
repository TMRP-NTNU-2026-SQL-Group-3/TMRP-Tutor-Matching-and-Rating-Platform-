<template>
  <div>
    <div v-if="loading" class="text-center py-8 text-gray-500">載入中...</div>

    <div v-else-if="match">
      <!-- Header with status -->
      <div class="flex items-center justify-between mb-6">
        <h1 class="text-2xl font-bold text-gray-900">配對詳情</h1>
        <StatusBadge :status="match.status" :label="match.status_label" />
      </div>

      <!-- Basic info card -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-6">
        <div class="grid grid-cols-2 gap-y-3 text-sm">
          <div class="text-gray-500">老師</div><div class="font-medium text-gray-900">{{ match.tutor_display_name }}</div>
          <div class="text-gray-500">學生</div><div class="font-medium text-gray-900">{{ match.student_name }}</div>
          <div class="text-gray-500">科目</div><div class="font-medium text-gray-900">{{ match.subject_name }}</div>
          <div class="text-gray-500">時薪</div><div class="font-medium text-gray-900">${{ match.hourly_rate }}/hr</div>
          <div class="text-gray-500">每週堂數</div><div class="font-medium text-gray-900">{{ match.sessions_per_week }}</div>
          <template v-if="match.want_trial">
            <div class="text-gray-500">試教</div><div class="font-medium text-gray-900">是</div>
          </template>
          <template v-if="match.invite_message">
            <div class="text-gray-500">備註</div><div class="font-medium text-gray-900">{{ match.invite_message }}</div>
          </template>
        </div>

        <div v-if="match.status === 'terminating' && match.termination_reason" class="mt-4 p-3 bg-red-50 rounded-lg">
          <p class="text-sm text-danger"><span class="font-semibold">終止原因：</span>{{ displayReason }}</p>
        </div>
      </div>

      <!-- Action buttons -->
      <div class="flex flex-wrap gap-2 mb-6">
        <button v-if="match.status === 'pending'" @click="doAction('cancel')"
          class="bg-gray-600 hover:bg-gray-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors">
          取消邀請
        </button>
        <button v-if="match.status === 'trial'" @click="doAction('confirm_trial')"
          class="bg-green-600 hover:bg-green-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors">
          確認正式合作
        </button>
        <button v-if="match.status === 'trial'" @click="doAction('reject_trial')"
          class="bg-red-600 hover:bg-red-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors">
          結束試教
        </button>
        <button v-if="match.status === 'active'" @click="doAction('pause')"
          class="bg-gray-600 hover:bg-gray-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors">
          暫停
        </button>
        <button v-if="match.status === 'active'" @click="showTerminate = true"
          class="bg-red-600 hover:bg-red-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors">
          申請終止
        </button>
        <button v-if="match.status === 'paused'" @click="doAction('resume')"
          class="bg-green-600 hover:bg-green-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors">
          恢復
        </button>
        <button v-if="match.status === 'paused'" @click="showTerminate = true"
          class="bg-red-600 hover:bg-red-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors">
          申請終止
        </button>
        <template v-if="match.status === 'terminating' && match.terminated_by !== userId">
          <button @click="doAction('agree_terminate')"
            class="bg-green-600 hover:bg-green-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors">
            同意終止
          </button>
          <button @click="doAction('disagree_terminate')"
            class="bg-gray-600 hover:bg-gray-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors">
            不同意
          </button>
        </template>
        <p v-if="match.status === 'terminating' && match.terminated_by === userId"
           class="text-sm text-gray-500 self-center">
          等待對方確認終止...
        </p>
      </div>

      <!-- Terminate form -->
      <ContractForm
        :visible="showTerminate"
        @submit="doTerminate"
        @cancel="showTerminate = false"
      />

      <p v-if="error" class="text-sm text-danger bg-red-50 rounded-lg p-3 mb-6">{{ error }}</p>

      <!-- Sessions -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">上課日誌</h2>
        <SessionTimeline :sessions="sessions" />
      </div>

      <!-- Progress Chart -->
      <ProgressChart v-if="exams.length" :exams="exams" class="mb-6" />

      <!-- Exams -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">考試紀錄</h2>
        <div v-if="exams.length" class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="border-b border-gray-200">
                <th class="px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">日期</th>
                <th class="px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">科目</th>
                <th class="px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">類型</th>
                <th class="px-4 py-2 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">分數</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
              <tr v-for="e in exams" :key="e.exam_id" class="hover:bg-gray-50 transition-colors">
                <td class="px-4 py-2.5 text-sm text-gray-700">{{ formatDate(e.exam_date) }}</td>
                <td class="px-4 py-2.5 text-sm text-gray-700">{{ e.subject_name }}</td>
                <td class="px-4 py-2.5 text-sm text-gray-700">{{ e.exam_type }}</td>
                <td class="px-4 py-2.5 text-sm text-gray-900 font-semibold text-right">{{ e.score }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="text-gray-400 text-sm">尚無考試紀錄</p>
      </div>

      <!-- Reviews -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">評價</h2>
        <ReviewList :reviews="reviews" />

        <!-- Write review -->
        <div v-if="canReview" class="mt-4">
          <button v-if="!showReviewForm" @click="showReviewForm = true"
            class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors">
            撰寫評價
          </button>
          <Transition
            enter-active-class="transition duration-200 ease-out"
            enter-from-class="opacity-0 -translate-y-2"
            enter-to-class="opacity-100 translate-y-0"
            leave-active-class="transition duration-150 ease-in"
            leave-from-class="opacity-100 translate-y-0"
            leave-to-class="opacity-0 -translate-y-2">
            <div v-if="showReviewForm" class="bg-gray-50 rounded-xl p-6 mt-4 space-y-4">
              <h3 class="text-lg font-semibold text-gray-900">評價老師</h3>
              <div class="grid grid-cols-2 gap-4">
                <div v-for="(label, idx) in ['教學能力', '溝通態度', '準時出席', '整體滿意度']" :key="idx">
                  <label class="block text-sm font-medium text-gray-700 mb-1">{{ label }}（1-5）</label>
                  <input v-model.number="reviewForm['rating_' + (idx + 1)]" type="number" min="1" max="5"
                    class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
                </div>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">個性評語</label>
                <textarea v-model="reviewForm.personality_comment" rows="2"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition"></textarea>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">評語</label>
                <textarea v-model="reviewForm.comment" rows="2"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition"></textarea>
              </div>
              <p v-if="reviewError" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ reviewError }}</p>
              <div class="flex gap-3">
                <button @click="submitReview" :disabled="reviewSubmitting"
                  class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
                  {{ reviewSubmitting ? '提交中...' : '提交評價' }}
                </button>
                <button @click="showReviewForm = false"
                  class="bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-lg px-4 py-2 text-sm font-medium transition-colors">
                  取消
                </button>
              </div>
            </div>
          </Transition>
        </div>
      </div>
    </div>

    <EmptyState v-else message="找不到此配對" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { matchesApi } from '@/api/matches'
import { sessionsApi } from '@/api/sessions'
import { examsApi } from '@/api/exams'
import { reviewsApi } from '@/api/reviews'
import StatusBadge from '@/components/common/StatusBadge.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import SessionTimeline from '@/components/session/SessionTimeline.vue'
import ReviewList from '@/components/review/ReviewList.vue'
import ContractForm from '@/components/match/ContractForm.vue'
import ProgressChart from '@/components/stats/ProgressChart.vue'

const route = useRoute()
const auth = useAuthStore()

const match = ref(null)
const sessions = ref([])
const exams = ref([])
const reviews = ref([])
const loading = ref(false)
const error = ref('')
const showTerminate = ref(false)

const showReviewForm = ref(false)
const reviewSubmitting = ref(false)
const reviewError = ref('')
const reviewForm = reactive({
  rating_1: 5, rating_2: 5, rating_3: 5, rating_4: 5,
  personality_comment: '', comment: ''
})

const userId = computed(() => auth.user?.user_id)

const canReview = computed(() => {
  if (!match.value) return false
  const alreadyReviewed = reviews.value.some(
    r => r.reviewer_user_id === userId.value && r.review_type === 'parent_to_tutor'
  )
  return !alreadyReviewed && ['active', 'ended'].includes(match.value.status)
})

const displayReason = computed(() => {
  const raw = match.value?.termination_reason || ''
  return raw.includes('|') ? raw.split('|').slice(1).join('|') : raw
})

function formatDate(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleDateString('zh-TW')
}

async function fetchMatch() {
  loading.value = true
  try {
    match.value = await matchesApi.getDetail(route.params.id)
    const [sessData, reviewData] = await Promise.all([
      sessionsApi.list({ match_id: route.params.id }),
      reviewsApi.list({ match_id: route.params.id }),
    ])
    sessions.value = sessData
    reviews.value = reviewData
    if (match.value.student_id) {
      exams.value = await examsApi.list({ student_id: match.value.student_id })
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function doAction(action) {
  error.value = ''
  try {
    await matchesApi.updateStatus(match.value.match_id, action)
    await fetchMatch()
  } catch (e) {
    error.value = e.message
  }
}

async function doTerminate(reason) {
  error.value = ''
  try {
    await matchesApi.updateStatus(match.value.match_id, 'terminate', reason)
    showTerminate.value = false
    await fetchMatch()
  } catch (e) {
    error.value = e.message
  }
}

async function submitReview() {
  reviewError.value = ''
  reviewSubmitting.value = true
  try {
    await reviewsApi.create({
      match_id: match.value.match_id,
      review_type: 'parent_to_tutor',
      ...reviewForm,
    })
    showReviewForm.value = false
    await fetchMatch()
  } catch (e) {
    reviewError.value = e.message
  } finally {
    reviewSubmitting.value = false
  }
}

onMounted(fetchMatch)
</script>
