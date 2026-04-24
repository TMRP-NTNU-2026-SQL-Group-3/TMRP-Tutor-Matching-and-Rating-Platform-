<template>
  <div>
    <!-- Loading skeleton -->
    <div v-if="loading" class="animate-pulse space-y-4"
         role="status" aria-live="polite" aria-label="載入配對詳情中">
      <div class="flex items-center justify-between">
        <div class="h-8 bg-gray-200 rounded w-32"></div>
        <div class="h-6 bg-gray-200 rounded-full w-20"></div>
      </div>
      <div class="bg-white rounded-xl border border-gray-100 p-6">
        <div class="space-y-3">
          <div class="h-4 bg-gray-200 rounded w-3/4"></div>
          <div class="h-4 bg-gray-200 rounded w-1/2"></div>
          <div class="h-4 bg-gray-200 rounded w-2/3"></div>
        </div>
      </div>
      <div class="bg-white rounded-xl border border-gray-100 p-6">
        <div class="h-4 bg-gray-200 rounded w-24 mb-4"></div>
        <div class="h-20 bg-gray-200 rounded"></div>
      </div>
      <span class="sr-only">載入中...</span>
    </div>

    <div v-else-if="match">
      <!-- Header with status -->
      <div class="flex items-center justify-between mb-6">
        <h1 class="text-2xl font-bold text-gray-900">配對詳情</h1>
        <div class="flex items-center gap-3">
          <button @click="printPage" type="button"
            class="text-sm text-gray-500 hover:text-gray-700 transition-colors print:hidden">
            列印
          </button>
          <StatusBadge :status="match.status" :label="match.status_label" />
        </div>
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
        <button v-if="match.status === 'pending'" @click="confirmAction('cancel', '確定要取消這筆邀請嗎？')" :disabled="actionLoading"
          class="bg-gray-600 hover:bg-gray-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
          {{ actionLoading ? '處理中...' : '取消邀請' }}
        </button>
        <button v-if="match.status === 'trial'" @click="showContractConfirm = true" :disabled="actionLoading"
          class="bg-green-600 hover:bg-green-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
          確認正式合作
        </button>
        <button v-if="match.status === 'trial'" @click="confirmAction('reject_trial', '確定要結束試教嗎？此配對將關閉，無法再恢復。')" :disabled="actionLoading"
          class="bg-red-600 hover:bg-red-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
          結束試教
        </button>
        <button v-if="match.status === 'active'" @click="doAction('pause')" :disabled="actionLoading"
          class="bg-gray-600 hover:bg-gray-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
          暫停
        </button>
        <button v-if="match.status === 'active'" @click="confirmTerminate()" :disabled="actionLoading"
          class="bg-red-600 hover:bg-red-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
          申請終止
        </button>
        <button v-if="match.status === 'paused'" @click="doAction('resume')" :disabled="actionLoading"
          class="bg-green-600 hover:bg-green-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
          恢復
        </button>
        <button v-if="match.status === 'paused'" @click="confirmTerminate()" :disabled="actionLoading"
          class="bg-red-600 hover:bg-red-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
          申請終止
        </button>
        <template v-if="match.status === 'terminating' && match.terminated_by !== userId">
          <button @click="confirmAction('agree_terminate', '確定要同意終止這筆配對嗎？')" :disabled="actionLoading"
            class="bg-green-600 hover:bg-green-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
            同意終止
          </button>
          <button @click="confirmAction('disagree_terminate', '確定要拒絕對方的終止申請嗎？')" :disabled="actionLoading"
            class="bg-gray-600 hover:bg-gray-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
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
        ref="contractFormRef"
        :visible="showTerminate"
        :submitting="actionLoading"
        @submit="handleTerminateSubmit"
        @cancel="handleTerminateCancel"
      />

      <!-- Spec Module D: trial → active contract confirmation -->
      <ContractConfirmModal
        :visible="showContractConfirm"
        :submitting="actionLoading"
        :defaults="contractDefaults"
        @submit="doConfirmTrial"
        @cancel="showContractConfirm = false"
      />

      <p v-if="error" role="alert" class="text-sm text-danger bg-red-50 rounded-lg p-3 mb-6">{{ error }}</p>

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
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div v-for="item in reviewLabels" :key="item.id">
                  <label class="block text-sm font-medium text-gray-700 mb-1">{{ item.label }}（1-5）</label>
                  <input v-model.number="reviewForm[item.id]" type="number" min="1" max="5"
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
              <p v-if="reviewError" role="alert" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ reviewError }}</p>
              <div class="flex gap-3">
                <button @click="handleSubmitReview" :disabled="reviewSubmitting"
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
import { useMatchDetail } from '@/composables/useMatchDetail'
import StatusBadge from '@/components/common/StatusBadge.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import SessionTimeline from '@/components/session/SessionTimeline.vue'
import ReviewList from '@/components/review/ReviewList.vue'
import ContractForm from '@/components/match/ContractForm.vue'
import ContractConfirmModal from '@/components/match/ContractConfirmModal.vue'
import ProgressChart from '@/components/stats/ProgressChart.vue'

const {
  match, sessions, exams, reviews,
  loading, error, actionLoading,
  showTerminate, showContractConfirm, userId, displayReason,
  fetchMatch, doAction, doTerminate, doConfirmTrial,
  showReviewForm, reviewSubmitting, reviewError, submitReview,
  formatDate,
} = useMatchDetail()

const contractDefaults = computed(() => ({
  hourly_rate: match.value?.hourly_rate ?? null,
  sessions_per_week: match.value?.sessions_per_week ?? null,
  start_date: match.value?.start_date
    ? String(match.value.start_date).slice(0, 10)
    : '',
}))

// Destructive action buttons require explicit confirmation to avoid mis-clicks.
function confirmAction(action, message) {
  if (!window.confirm(message)) return
  doAction(action)
}
function confirmTerminate() {
  if (!window.confirm('申請終止後，對方確認即會關閉配對。是否繼續？')) return
  showTerminate.value = true
}

// Contract form
const contractFormRef = ref(null)
function handleTerminateCancel() {
  showTerminate.value = false
  contractFormRef.value?.reset()
}
async function handleTerminateSubmit(reason) {
  if (!window.confirm('確定要送出終止申請嗎？送出後，對方同意即會關閉配對。')) return
  await doTerminate(reason)
  contractFormRef.value?.reset()
}

function printPage() { window.print() }

const reviewLabels = [
  { id: 'rating_1', label: '教學能力' },
  { id: 'rating_2', label: '溝通態度' },
  { id: 'rating_3', label: '準時出席' },
  { id: 'rating_4', label: '整體滿意度' },
]

const reviewForm = reactive({
  rating_1: 5, rating_2: 5, rating_3: 5, rating_4: 5,
  personality_comment: '', comment: ''
})

const canReview = computed(() => {
  if (!match.value) return false
  const alreadyReviewed = reviews.value.some(
    r => r.reviewer_user_id === userId.value && r.review_type === 'parent_to_tutor'
  )
  // Reviews are only allowed in active/paused/ended states (not during terminating).
  return !alreadyReviewed && ['active', 'paused', 'ended'].includes(match.value?.status)
})

async function handleSubmitReview() {
  // T-WEB-02: 驗證評分範圍
  for (let i = 1; i <= 4; i++) {
    const val = reviewForm['rating_' + i]
    if (val == null || val < 1 || val > 5) {
      reviewError.value = `評分項目 ${i} 必須在 1-5 之間`
      return
    }
  }
  await submitReview({ review_type: 'parent_to_tutor', ...reviewForm })
  if (!reviewError.value) {
    Object.assign(reviewForm, {
      rating_1: 5, rating_2: 5, rating_3: 5, rating_4: 5,
      personality_comment: '', comment: ''
    })
  }
}

onMounted(fetchMatch)
</script>
