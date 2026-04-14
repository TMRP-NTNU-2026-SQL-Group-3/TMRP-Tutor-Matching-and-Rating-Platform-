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
        <StatusBadge :status="match.status" :label="match.status_label" />
      </div>

      <!-- Basic info card -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-6">
        <div class="grid grid-cols-2 gap-y-3 text-sm">
          <div class="text-gray-500">學生</div><div class="font-medium text-gray-900">{{ match.student_name }}</div>
          <div class="text-gray-500">科目</div><div class="font-medium text-gray-900">{{ match.subject_name }}</div>
          <div class="text-gray-500">時薪</div><div class="font-medium text-gray-900">${{ match.hourly_rate }}/hr</div>
          <div class="text-gray-500">每週堂數</div><div class="font-medium text-gray-900">{{ match.sessions_per_week }}</div>
          <template v-if="match.want_trial">
            <div class="text-gray-500">試教</div><div class="font-medium text-gray-900">是</div>
          </template>
          <template v-if="match.invite_message">
            <div class="text-gray-500">家長備註</div><div class="font-medium text-gray-900">{{ match.invite_message }}</div>
          </template>
        </div>

        <div v-if="match.status === 'terminating' && match.termination_reason" class="mt-4 p-3 bg-red-50 rounded-lg">
          <p class="text-sm text-danger"><span class="font-semibold">終止原因：</span>{{ displayReason }}</p>
        </div>
      </div>

      <!-- Action buttons -->
      <div class="flex flex-wrap gap-2 mb-6">
        <button v-if="match.status === 'pending'" @click="doAction('accept')" :disabled="actionLoading"
          class="bg-green-600 hover:bg-green-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
          {{ actionLoading ? '處理中...' : '接受邀請' }}
        </button>
        <button v-if="match.status === 'pending'" @click="confirmAction('reject', '確定要拒絕這筆邀請嗎？')" :disabled="actionLoading"
          class="bg-red-600 hover:bg-red-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
          拒絕邀請
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
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-semibold text-gray-900">上課日誌</h2>
          <button v-if="['active', 'trial'].includes(match.status) && !showSessionForm"
            @click="showSessionForm = true"
            class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-3 py-1.5 text-sm font-medium transition-colors">
            + 新增
          </button>
        </div>

        <!-- Session form -->
        <SessionForm ref="sessionFormRef"
          :visible="showSessionForm"
          :submitting="sessionSubmitting"
          :error="sessionError"
          @submit="submitSession"
          @cancel="showSessionForm = false"
        />

        <SessionTimeline :sessions="sessions" :show-visibility="true" />
      </div>

      <!-- Progress Chart -->
      <ProgressChart v-if="exams.length" :exams="exams" class="mb-6" />

      <!-- Exams -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-6">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-lg font-semibold text-gray-900">考試紀錄</h2>
          <button v-if="['active', 'trial'].includes(match.status) && !showExamForm"
            @click="showExamForm = true"
            class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-3 py-1.5 text-sm font-medium transition-colors">
            + 新增
          </button>
        </div>

        <!-- Exam form -->
        <Transition
          enter-active-class="transition duration-200 ease-out"
          enter-from-class="opacity-0 -translate-y-2"
          enter-to-class="opacity-100 translate-y-0"
          leave-active-class="transition duration-150 ease-in"
          leave-from-class="opacity-100 translate-y-0"
          leave-to-class="opacity-0 -translate-y-2">
          <div v-if="showExamForm" class="bg-gray-50 rounded-xl p-5 mb-4 space-y-4">
            <h3 class="font-semibold text-gray-900">新增考試紀錄</h3>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">日期 *</label>
                <input v-model="examForm.exam_date" type="date"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">類型 *</label>
                <select v-model="examForm.exam_type"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition">
                  <option value="段考">段考</option>
                  <option value="小考">小考</option>
                  <option value="模擬考">模擬考</option>
                  <option value="其他">其他</option>
                </select>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">分數 *</label>
                <input v-model.number="examForm.score" type="number" min="0"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
              </div>
              <div class="flex items-end pb-2">
                <div class="flex items-center gap-2">
                  <input v-model="examForm.visible_to_parent" type="checkbox" id="exam-visible"
                    class="rounded border-gray-300 text-primary-600 focus:ring-primary-500" />
                  <label for="exam-visible" class="text-sm text-gray-700">家長可見</label>
                </div>
              </div>
            </div>
            <p v-if="examError" role="alert" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ examError }}</p>
            <div class="flex gap-3">
              <button @click="submitExam" :disabled="examSubmitting"
                class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
                {{ examSubmitting ? '新增中...' : '確認新增' }}
              </button>
              <button @click="showExamForm = false"
                class="bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-lg px-4 py-2 text-sm font-medium transition-colors">
                取消
              </button>
            </div>
          </div>
        </Transition>

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
        <div v-if="canReviewParent || canReviewStudent" class="mt-4">
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
              <h3 class="text-lg font-semibold text-gray-900">撰寫評價</h3>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">評價對象</label>
                <select v-model="reviewForm.review_type"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition">
                  <option v-if="canReviewParent" value="tutor_to_parent">評價家長</option>
                  <option v-if="canReviewStudent" value="tutor_to_student">評價學生</option>
                </select>
              </div>
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
import { useToastStore } from '@/stores/toast'
import { sessionsApi } from '@/api/sessions'
import { examsApi } from '@/api/exams'
import StatusBadge from '@/components/common/StatusBadge.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import SessionTimeline from '@/components/session/SessionTimeline.vue'
import SessionForm from '@/components/session/SessionForm.vue'
import ReviewList from '@/components/review/ReviewList.vue'
import ContractForm from '@/components/match/ContractForm.vue'
import ContractConfirmModal from '@/components/match/ContractConfirmModal.vue'
import ProgressChart from '@/components/stats/ProgressChart.vue'

const toast = useToastStore()

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
  await doTerminate(reason)
  contractFormRef.value?.reset()
}

// Session form
const sessionFormRef = ref(null)
const showSessionForm = ref(false)
const sessionSubmitting = ref(false)
const sessionError = ref('')

// Exam form
const showExamForm = ref(false)
const examSubmitting = ref(false)
const examError = ref('')
const examForm = reactive({
  exam_date: '', exam_type: '段考', score: 0, visible_to_parent: true,
})

// Review form
const reviewForm = reactive({
  review_type: 'tutor_to_parent',
  rating_1: 5, rating_2: 5, rating_3: 5, rating_4: 5,
  personality_comment: '', comment: ''
})

const TUTOR_TO_PARENT_LABELS = [
  { id: 'rating_1', label: '配合度' },
  { id: 'rating_2', label: '溝通態度' },
  { id: 'rating_3', label: '準時付費' },
  { id: 'rating_4', label: '整體滿意度' },
]
const TUTOR_TO_STUDENT_LABELS = [
  { id: 'rating_1', label: '學習態度' },
  { id: 'rating_2', label: '完成作業' },
  { id: 'rating_3', label: '課堂表現' },
  { id: 'rating_4', label: '整體進步' },
]
const reviewLabels = computed(() =>
  reviewForm.review_type === 'tutor_to_parent'
    ? TUTOR_TO_PARENT_LABELS
    : TUTOR_TO_STUDENT_LABELS
)

const canReviewParent = computed(() => {
  if (!match.value) return false
  return !reviews.value.some(r => r.reviewer_user_id === userId.value && r.review_type === 'tutor_to_parent')
    && ['active', 'paused', 'ended'].includes(match.value.status)
})

const canReviewStudent = computed(() => {
  if (!match.value) return false
  return !reviews.value.some(r => r.reviewer_user_id === userId.value && r.review_type === 'tutor_to_student')
    && ['active', 'paused', 'ended'].includes(match.value.status)
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
  await submitReview({ ...reviewForm })
  if (!reviewError.value) {
    // T-WEB-06: 保留當前選擇的 review_type，而非強制覆蓋
    const currentType = reviewForm.review_type
    Object.assign(reviewForm, {
      review_type: currentType,
      rating_1: 5, rating_2: 5, rating_3: 5, rating_4: 5,
      personality_comment: '', comment: ''
    })
  }
}

async function submitSession(formData) {
  sessionError.value = ''
  if (!formData.session_date || !formData.content_summary?.trim()) {
    sessionError.value = '日期和教學內容為必填'
    return
  }
  sessionSubmitting.value = true
  try {
    await sessionsApi.create({
      match_id: match.value.match_id,
      ...formData,
    })
    // Only close the form once the refetch confirms the new session is in the
    // list. fetchMatch swallows its own errors (sets error.value + toasts) and
    // returns false on failure, so if we closed unconditionally the user could
    // see the form vanish without their entry appearing anywhere.
    const refreshed = await fetchMatch()
    if (refreshed) {
      showSessionForm.value = false
      sessionFormRef.value?.reset()
      toast.success('上課日誌已新增')
    } else {
      toast.success('上課日誌已新增，但列表更新失敗，請手動重新整理')
    }
  } catch (e) {
    sessionError.value = e.message
    toast.error(e.message)
  } finally {
    sessionSubmitting.value = false
  }
}

async function submitExam() {
  examError.value = ''
  if (!examForm.exam_date) {
    examError.value = '日期為必填'
    return
  }
  // Bug #24: match 載入失敗時 student_id / subject_id 會是 undefined，
  // 提早攔截避免送出含 null id 的 API 請求觸發後端 500
  if (!match.value || match.value.student_id == null || match.value.subject_id == null) {
    examError.value = '配對資料尚未載入完成，請稍候再試'
    return
  }
  examSubmitting.value = true
  try {
    await examsApi.create({
      student_id: match.value.student_id,
      subject_id: match.value.subject_id,
      exam_date: examForm.exam_date,
      exam_type: examForm.exam_type,
      score: examForm.score,
      visible_to_parent: examForm.visible_to_parent,
    })
    showExamForm.value = false
    examForm.exam_date = ''
    examForm.score = 0
    examForm.exam_type = '段考'
    examForm.visible_to_parent = true
    toast.success('考試紀錄已新增')
    await fetchMatch()
  } catch (e) {
    examError.value = e.message
    toast.error(e.message)
  } finally {
    examSubmitting.value = false
  }
}

onMounted(fetchMatch)
</script>
