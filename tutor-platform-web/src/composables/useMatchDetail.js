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
  let _fetchId = 0

  async function fetchMatch() {
    const currentFetchId = ++_fetchId

    // Bug #26: 提早驗證路由參數，避免直接訪問 /parent/match/abc 時送出無效 ID
    const rawId = route.params.id
    const matchId = Number(rawId)
    if (!rawId || !Number.isInteger(matchId) || matchId <= 0) {
      error.value = '配對編號格式錯誤'
      loading.value = false
      toast.error('配對編號格式錯誤')
      return
    }

    // 首次載入才顯示 skeleton，後續重新整理不閃爍
    if (!match.value) loading.value = true
    error.value = ''
    try {
      const detail = await matchesApi.getDetail(matchId)
      if (currentFetchId !== _fetchId) return  // 已有更新的請求，丟棄此結果
      match.value = detail
      const [sessData, reviewData] = await Promise.all([
        sessionsApi.list({ match_id: matchId }),
        reviewsApi.list({ match_id: matchId }),
      ])
      if (currentFetchId !== _fetchId) return
      sessions.value = sessData
      reviews.value = reviewData
      if (match.value.student_id) {
        const examData = await examsApi.list({ student_id: match.value.student_id })
        if (currentFetchId !== _fetchId) return
        // The exams API returns every exam for the student (across tutors/subjects).
        // Restrict to this match's subject so the trend chart and "本配對考試紀錄"
        // panel don't leak data from other matches.
        const subjectId = match.value.subject_id
        exams.value = subjectId
          ? examData.filter(e => e.subject_id === subjectId)
          : examData
      }
    } catch (e) {
      if (currentFetchId !== _fetchId) return
      error.value = e.message
      toast.error('載入配對資料失敗')
    } finally {
      if (currentFetchId === _fetchId) loading.value = false
    }
  }

  // ── 狀態操作 ──
  async function doAction(action) {
    if (!match.value || actionLoading.value) return
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
    if (!match.value || actionLoading.value) return
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
    if (reviewSubmitting.value) return
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
