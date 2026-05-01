<template>
  <div>
    <PageHeader title="編輯個人檔案" />

    <div v-if="loading" class="text-center py-8 text-gray-500">載入中...</div>

    <form v-else @submit.prevent="handleSave" class="space-y-6">
      <!-- Intro & Experience -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-4">
        <h2 class="text-lg font-semibold text-gray-900">基本資訊</h2>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">自我介紹</label>
          <textarea v-model="form.self_intro" rows="4"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition"></textarea>
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">教學經驗</label>
          <textarea v-model="form.teaching_experience" rows="4"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition"></textarea>
        </div>
      </div>

      <!-- School info -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-4">
        <h2 class="text-lg font-semibold text-gray-900">學歷資訊</h2>
        <div class="grid md:grid-cols-3 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">大學</label>
            <input v-model="form.university" type="text"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">科系</label>
            <input v-model="form.department" type="text"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">年級</label>
            <input v-model.number="form.grade_year" type="number" min="1" max="10"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
          </div>
        </div>
      </div>

      <!-- Subjects -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-4">
        <h2 class="text-lg font-semibold text-gray-900">授課科目</h2>
        <div v-for="(item, idx) in subjectList" :key="item._uid" class="flex items-center gap-3">
          <select v-model="item.subject_id"
            :aria-invalid="isDuplicateSubject(item, idx) || null"
            class="flex-1 rounded-lg border px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition"
            :class="isDuplicateSubject(item, idx) ? 'border-red-400' : 'border-gray-300'">
            <option :value="null" disabled>選擇科目</option>
            <option v-for="s in availableSubjectsFor(item)" :key="s.subject_id" :value="s.subject_id">
              {{ s.subject_name }}
            </option>
          </select>
          <div class="flex items-center gap-1">
            <span class="text-sm text-gray-500">$</span>
            <input v-model.number="item.hourly_rate" type="number" min="1" placeholder="時薪"
              class="w-24 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
            <span class="text-sm text-gray-500">/hr</span>
          </div>
          <button type="button" @click="subjectList.splice(idx, 1)"
            class="text-red-500 hover:text-red-700 text-sm font-medium transition-colors">移除</button>
        </div>
        <p v-if="hasDuplicateSubjects" role="alert"
          class="text-xs text-red-600">同一科目不能重複加入，請先移除或更改重複項。</p>
        <button type="button" @click="addSubjectRow" :disabled="!hasFreeSubject"
          :title="!hasFreeSubject ? '已達科目上限，請先移除現有科目再新增' : undefined"
          class="text-primary-600 hover:text-primary-700 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
          + 新增科目
        </button>
      </div>

      <!-- Availability -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-4">
        <h2 class="text-lg font-semibold text-gray-900">可用時段</h2>
        <p class="text-xs text-gray-500">家長會看到這些時段以安排課程</p>
        <div v-for="(slot, idx) in availabilityList" :key="slot._uid" class="flex items-center gap-3 flex-wrap">
          <select v-model.number="slot.day_of_week"
            class="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition">
            <option v-for="d in dayOptions" :key="d.value" :value="d.value">{{ d.label }}</option>
          </select>
          <input v-model="slot.start_time" type="time"
            class="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
          <span class="text-sm text-gray-500">至</span>
          <input v-model="slot.end_time" type="time"
            class="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
          <button type="button" @click="availabilityList.splice(idx, 1)"
            class="text-red-500 hover:text-red-700 text-sm font-medium transition-colors">移除</button>
        </div>
        <button type="button" @click="addAvailabilityRow"
          class="text-primary-600 hover:text-primary-700 text-sm font-medium transition-colors">+ 新增時段</button>
        <div v-if="previewSlots.length" class="pt-3 border-t border-gray-100 space-y-2">
          <p class="text-xs text-gray-500">預覽（家長看到的樣式）</p>
          <AvailabilityCalendar :slots="previewSlots" />
        </div>
      </div>

      <!-- Settings -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-4">
        <h2 class="text-lg font-semibold text-gray-900">偏好設定</h2>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">最大收生數</label>
          <input v-model.number="form.max_students" type="number" min="1" max="50"
            class="w-32 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition" />
        </div>
      </div>

      <!-- Visibility Settings -->
      <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-lg font-semibold text-gray-900">公開欄位設定</h2>
            <p class="text-xs text-gray-500 mt-1">控制哪些個人資料對家長公開顯示</p>
          </div>
          <button type="button" @click="handleSaveVisibility" :disabled="savingVisibility"
            class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50">
            {{ savingVisibility ? '儲存中...' : '儲存公開設定' }}
          </button>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label for="vis-university" class="flex items-center gap-3 p-3 rounded-lg border border-gray-100 hover:bg-gray-50 transition-colors cursor-pointer">
            <input id="vis-university" v-model="form.show_university" type="checkbox"
              aria-describedby="vis-university-desc"
              class="rounded border-gray-300 text-primary-600 focus:ring-primary-500" />
            <div>
              <span class="text-sm font-medium text-gray-700">大學</span>
              <p id="vis-university-desc" class="text-xs text-gray-400">{{ form.university || '未填寫' }}</p>
            </div>
          </label>
          <label for="vis-department" class="flex items-center gap-3 p-3 rounded-lg border border-gray-100 hover:bg-gray-50 transition-colors cursor-pointer">
            <input id="vis-department" v-model="form.show_department" type="checkbox"
              aria-describedby="vis-department-desc"
              class="rounded border-gray-300 text-primary-600 focus:ring-primary-500" />
            <div>
              <span class="text-sm font-medium text-gray-700">科系</span>
              <p id="vis-department-desc" class="text-xs text-gray-400">{{ form.department || '未填寫' }}</p>
            </div>
          </label>
          <label for="vis-grade-year" class="flex items-center gap-3 p-3 rounded-lg border border-gray-100 hover:bg-gray-50 transition-colors cursor-pointer">
            <input id="vis-grade-year" v-model="form.show_grade_year" type="checkbox"
              aria-describedby="vis-grade-year-desc"
              class="rounded border-gray-300 text-primary-600 focus:ring-primary-500" />
            <div>
              <span class="text-sm font-medium text-gray-700">年級</span>
              <p id="vis-grade-year-desc" class="text-xs text-gray-400">{{ form.grade_year ? `${form.grade_year} 年級` : '未填寫' }}</p>
            </div>
          </label>
          <label for="vis-hourly-rate" class="flex items-center gap-3 p-3 rounded-lg border border-gray-100 hover:bg-gray-50 transition-colors cursor-pointer">
            <input id="vis-hourly-rate" v-model="form.show_hourly_rate" type="checkbox"
              aria-describedby="vis-hourly-rate-desc"
              class="rounded border-gray-300 text-primary-600 focus:ring-primary-500" />
            <div>
              <span class="text-sm font-medium text-gray-700">時薪</span>
              <p id="vis-hourly-rate-desc" class="text-xs text-gray-400">各科目的時薪費率</p>
            </div>
          </label>
          <label for="vis-subjects" class="flex items-center gap-3 p-3 rounded-lg border border-gray-100 hover:bg-gray-50 transition-colors cursor-pointer">
            <input id="vis-subjects" v-model="form.show_subjects" type="checkbox"
              aria-describedby="vis-subjects-desc"
              class="rounded border-gray-300 text-primary-600 focus:ring-primary-500" />
            <div>
              <span class="text-sm font-medium text-gray-700">授課科目</span>
              <p id="vis-subjects-desc" class="text-xs text-gray-400">教授的科目列表</p>
            </div>
          </label>
        </div>
        <p v-if="visibilitySuccess" role="status" class="text-sm text-green-700 bg-green-50 rounded-lg p-3">{{ visibilitySuccess }}</p>
        <p v-if="visibilityError" role="alert" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ visibilityError }}</p>
      </div>

      <!-- Messages -->
      <p v-if="error" role="alert" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ error }}</p>
      <p v-if="success" role="status" class="text-sm text-green-700 bg-green-50 rounded-lg p-3">{{ success }}</p>

      <button type="submit" :disabled="saving"
        class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-6 py-2.5 text-sm font-medium transition-colors disabled:opacity-50">
        {{ saving ? '儲存中...' : '儲存' }}
      </button>
    </form>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { tutorsApi } from '@/api/tutors'
import { subjectsApi } from '@/api/subjects'
import PageHeader from '@/components/common/PageHeader.vue'
import AvailabilityCalendar from '@/components/tutor/AvailabilityCalendar.vue'

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const success = ref('')
const allSubjects = ref([])
const subjectList = ref([])
const availabilityList = ref([])
const savingVisibility = ref(false)
const visibilitySuccess = ref('')
const visibilityError = ref('')

const dayOptions = [
  { value: 0, label: '週日' },
  { value: 1, label: '週一' },
  { value: 2, label: '週二' },
  { value: 3, label: '週三' },
  { value: 4, label: '週四' },
  { value: 5, label: '週五' },
  { value: 6, label: '週六' },
]

function _hhmm(t) {
  if (!t) return ''
  const s = String(t)
  return s.length >= 5 ? s.slice(0, 5) : s
}

// Stable client-side id for v-for keys on mutable lists. The DB rows don't
// carry a standalone PK exposed to the frontend (subject rows use a composite
// key, availability has no id in the response), so we mint one per row.
let _nextUid = 0
const mintUid = () => ++_nextUid

let isMounted = true
// F-04: track the success-banner timeout so we can clear it if the user
// unmounts mid-flight (otherwise the callback fires on a dead component).
let successTimer = null
let visibilityTimer = null

const isDirty = ref(false)
let _loaded = false

function handleBeforeUnload(e) {
  if (!isDirty.value) return
  e.preventDefault()
  e.returnValue = ''
}

onBeforeRouteLeave((to, from, next) => {
  if (isDirty.value && !window.confirm('您有未儲存的變更，確定要離開嗎？')) {
    next(false)
  } else {
    next()
  }
})

onUnmounted(() => {
  isMounted = false
  window.removeEventListener('beforeunload', handleBeforeUnload)
  if (successTimer) {
    clearTimeout(successTimer)
    successTimer = null
  }
  if (visibilityTimer) {
    clearTimeout(visibilityTimer)
    visibilityTimer = null
  }
})

const form = reactive({
  self_intro: '',
  teaching_experience: '',
  university: '',
  department: '',
  grade_year: null,
  max_students: 5,
  show_university: true,
  show_department: true,
  show_grade_year: true,
  show_hourly_rate: true,
  show_subjects: true,
})

watch(
  [() => ({ ...form }), subjectList, availabilityList],
  () => { if (_loaded) isDirty.value = true },
  { deep: true }
)

// U-11: The (tutor_id, subject_id) pair is a composite PK in tutor_subjects,
// so duplicates are rejected by the DB. Filter them out before we even offer a
// "new row" button, and surface a clear inline error if any slip through.
function isDuplicateSubject(item, idx) {
  if (item.subject_id == null) return false
  return subjectList.value.some((s, i) => i !== idx && s.subject_id === item.subject_id)
}

const hasDuplicateSubjects = computed(() => {
  const seen = new Set()
  for (const s of subjectList.value) {
    if (s.subject_id == null) continue
    if (seen.has(s.subject_id)) return true
    seen.add(s.subject_id)
  }
  return false
})

const chosenSubjectIds = computed(() =>
  new Set(subjectList.value.map(s => s.subject_id).filter(id => id != null))
)

function availableSubjectsFor(item) {
  // Keep the already-chosen value visible in its own dropdown so users can
  // re-select it, but hide any subject that is picked by another row.
  return allSubjects.value.filter(s =>
    s.subject_id === item.subject_id || !chosenSubjectIds.value.has(s.subject_id)
  )
}

const hasFreeSubject = computed(() => chosenSubjectIds.value.size < allSubjects.value.length)

const previewSlots = computed(() =>
  availabilityList.value
    .filter(s => s.start_time && s.end_time && s.start_time < s.end_time)
    .map(s => ({
      availability_id: s._uid,
      day_of_week: Number(s.day_of_week),
      start_time: s.start_time,
      end_time: s.end_time,
    }))
)

function addSubjectRow() {
  if (!hasFreeSubject.value) return
  subjectList.value.push({ _uid: mintUid(), subject_id: null, hourly_rate: null })
}

function addAvailabilityRow() {
  availabilityList.value.push({
    _uid: mintUid(), day_of_week: 1, start_time: '19:00', end_time: '21:00',
  })
}

async function handleSaveVisibility() {
  if (savingVisibility.value) return
  visibilityError.value = ''
  visibilitySuccess.value = ''
  savingVisibility.value = true
  try {
    await tutorsApi.updateVisibility({
      show_university: form.show_university,
      show_department: form.show_department,
      show_grade_year: form.show_grade_year,
      show_hourly_rate: form.show_hourly_rate,
      show_subjects: form.show_subjects,
    })
    visibilitySuccess.value = '公開設定已更新'
    if (visibilityTimer) clearTimeout(visibilityTimer)
    visibilityTimer = setTimeout(() => {
      visibilitySuccess.value = ''
      visibilityTimer = null
    }, 3000)
  } catch (e) {
    visibilityError.value = e.message
  } finally {
    savingVisibility.value = false
  }
}

async function handleSave() {
  // F-04: explicit re-entry guard — the disabled button alone leaves a tiny
  // window where a fast double-click (or Enter-spam) can re-enter before
  // saving.value flips, firing duplicate PUTs across three endpoints.
  if (saving.value) return
  error.value = ''
  success.value = ''
  if (hasDuplicateSubjects.value) {
    error.value = '同一科目不能重複加入'
    return
  }
  saving.value = true
  try {
    const errors = []
    let profileSaved = false

    try {
      await tutorsApi.updateProfile(form)
      profileSaved = true
    } catch (e) {
      errors.push('基本資料儲存失敗：' + e.message)
    }

    const validSubjects = subjectList.value
      .filter(s => s.subject_id && s.hourly_rate)
      .map(s => ({ subject_id: s.subject_id, hourly_rate: s.hourly_rate }))
    try {
      await tutorsApi.updateSubjects({ subjects: validSubjects })
    } catch (e) {
      errors.push('科目設定失敗：' + e.message)
    }

    const validSlots = availabilityList.value
      .filter(s => s.start_time && s.end_time && s.start_time < s.end_time)
      .map(s => ({
        day_of_week: Number(s.day_of_week),
        start_time: _hhmm(s.start_time),
        end_time: _hhmm(s.end_time),
      }))
    try {
      await tutorsApi.updateAvailability({ slots: validSlots })
    } catch (e) {
      errors.push('時段設定失敗：' + e.message)
    }

    if (profileSaved) isDirty.value = false
    if (errors.length) {
      error.value = profileSaved
        ? '基本資料已儲存，但' + errors.join('；')
        : errors.join('；')
    } else {
      success.value = '個人檔案已更新'
    }
    // Auto-clear the success banner after 3 s so a stale message does not mislead on the next save.
    // Store the handle and cancel any in-flight timer: unmounting mid-flight or a second save within 3 s must not leave a dangling callback.
    if (successTimer) clearTimeout(successTimer)
    successTimer = setTimeout(() => {
      success.value = ''
      successTimer = null
    }, 3000)
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  loading.value = true
  try {
    const [detail, subjects] = await Promise.all([
      tutorsApi.getMyProfile(),
      subjectsApi.list(),
    ])
    if (!isMounted) return

    form.self_intro = detail.self_intro || ''
    form.teaching_experience = detail.teaching_experience || ''
    form.university = detail.university || ''
    form.department = detail.department || ''
    form.grade_year = detail.grade_year || null
    form.max_students = detail.max_students || 5
    form.show_university = detail.show_university ?? true
    form.show_department = detail.show_department ?? true
    form.show_grade_year = detail.show_grade_year ?? true
    form.show_hourly_rate = detail.show_hourly_rate ?? true
    form.show_subjects = detail.show_subjects ?? true

    allSubjects.value = subjects
    subjectList.value = (detail.subjects || []).map(s => ({
      _uid: mintUid(),
      subject_id: s.subject_id,
      hourly_rate: s.hourly_rate,
    }))
    availabilityList.value = (detail.availability || []).map(a => ({
      _uid: mintUid(),
      day_of_week: a.day_of_week,
      start_time: _hhmm(a.start_time),
      end_time: _hhmm(a.end_time),
    }))
    await nextTick()
    _loaded = true
  } catch (e) {
    if (isMounted) error.value = e.message
  } finally {
    // Reset loading unconditionally: the ref setter is side-effect-free on an unmounted component, and guarantees a clean state on the next mount.
    loading.value = false
  }
})
</script>
