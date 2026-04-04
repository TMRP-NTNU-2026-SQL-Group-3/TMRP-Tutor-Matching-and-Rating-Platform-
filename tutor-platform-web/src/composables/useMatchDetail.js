import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import { matchesApi } from '@/api/matches'
import { sessionsApi } from '@/api/sessions'
import { examsApi } from '@/api/exams'
import { reviewsApi } from '@/api/reviews'

/**
 * 共用的配對詳情邏輯 — 家長版與家教版共用。
 */
export function useMatchDetail() {
  const route = useRoute()
  const auth = useAuthStore()
  const toast = useToastStore()

  // ── 核心資料 ──
  const match = ref(null)
  const sessions = ref([])
  const exams = ref([])
  const reviews = ref([])
  const loading = ref(false)
  const error = ref('')
  const showTerminate = ref(false)
  const actionLoading = ref(false)

  const userId = computed(() => auth.user?.user_id)

  const displayReason = computed(() => {
    const raw = match.value?.termination_reason || ''
    return raw.includes('|') ? raw.split('|').slice(1).join('|') : raw
  })

  // ── 資料載入 ──
  async function fetchMatch() {
    // 首次載入才顯示 skeleton，後續重新整理不閃爍
    if (!match.value) loading.value = true
    error.value = ''
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
      toast.error('載入配對資料失敗')
    } finally {
      loading.value = false
    }
  }

  // ── 狀態操作 ──
  async function doAction(action) {
    error.value = ''
    actionLoading.value = true
    try {
      await matchesApi.updateStatus(match.value.match_id, action)
      toast.success('操作成功')
      await fetchMatch()
    } catch (e) {
      error.value = e.message
      toast.error(e.message)
    } finally {
      actionLoading.value = false
    }
  }

  async function doTerminate(reason) {
    error.value = ''
    actionLoading.value = true
    try {
      await matchesApi.updateStatus(match.value.match_id, 'terminate', reason)
      showTerminate.value = false
      toast.success('終止申請已送出')
      await fetchMatch()
    } catch (e) {
      error.value = e.message
      toast.error(e.message)
    } finally {
      actionLoading.value = false
    }
  }

  // ── 評價 ──
  const showReviewForm = ref(false)
  const reviewSubmitting = ref(false)
  const reviewError = ref('')

  async function submitReview(payload) {
    reviewError.value = ''
    reviewSubmitting.value = true
    try {
      await reviewsApi.create({
        match_id: match.value.match_id,
        ...payload,
      })
      showReviewForm.value = false
      toast.success('評價已提交')
      await fetchMatch()
    } catch (e) {
      reviewError.value = e.message
      toast.error(e.message)
    } finally {
      reviewSubmitting.value = false
    }
  }

  // ── 工具 ──
  function formatDate(dt) {
    if (!dt) return ''
    return new Date(dt).toLocaleDateString('zh-TW')
  }

  return {
    match, sessions, exams, reviews,
    loading, error, actionLoading,
    showTerminate, userId, displayReason,
    fetchMatch, doAction, doTerminate,
    showReviewForm, reviewSubmitting, reviewError, submitReview,
    formatDate,
  }
}
