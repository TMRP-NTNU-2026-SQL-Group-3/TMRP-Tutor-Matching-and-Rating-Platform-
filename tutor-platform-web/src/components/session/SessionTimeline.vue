<template>
  <div v-if="sessions.length" class="border-l-2 border-primary-200 pl-4 space-y-4">
    <div v-for="s in sessions" :key="s.session_id">
      <div class="flex items-center gap-3 mb-1">
        <span class="px-2 py-0.5 bg-primary-50 text-primary-700 text-xs rounded-full font-medium">
          {{ formatDate(s.session_date) }}
        </span>
        <span class="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded-full">
          {{ s.hours }} 小時
        </span>
        <span v-if="showVisibility && (!s.visible_to_parent || s.visible_to_parent === 0)"
              class="px-2 py-0.5 bg-amber-100 text-amber-700 text-xs rounded-full">
          家長不可見
        </span>
        <button @click="toggleEditLogs(s.session_id)"
          class="px-2 py-0.5 text-xs text-gray-500 hover:text-primary-600 transition-colors underline-offset-2 hover:underline">
          {{ editLogOpen[s.session_id] ? '收起修改紀錄' : '修改紀錄' }}
        </button>
        <template v-if="editable">
          <button @click="startEdit(s)"
            class="px-2 py-0.5 text-xs text-primary-600 hover:text-primary-800 font-medium transition-colors">
            編輯
          </button>
          <button @click="confirmDelete(s.session_id)"
            class="px-2 py-0.5 text-xs text-red-600 hover:text-red-800 font-medium transition-colors">
            刪除
          </button>
        </template>
      </div>

      <!-- Inline edit form -->
      <div v-if="editingSessionId === s.session_id" class="bg-gray-50 rounded-xl p-4 mb-2 space-y-3">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1">日期</label>
            <input v-model="editForm.session_date" type="date"
              class="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1">時數</label>
            <input v-model.number="editForm.hours" type="number" min="0.5" max="24" step="0.5"
              class="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none" />
          </div>
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">教學內容</label>
          <textarea v-model="editForm.content_summary" rows="2"
            class="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"></textarea>
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">作業</label>
          <textarea v-model="editForm.homework" rows="1"
            class="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"></textarea>
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">學生表現</label>
          <textarea v-model="editForm.student_performance" rows="1"
            class="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"></textarea>
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">下次計畫</label>
          <textarea v-model="editForm.next_plan" rows="1"
            class="w-full rounded border border-gray-300 px-2 py-1 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"></textarea>
        </div>
        <div class="flex items-center gap-2">
          <input v-model="editForm.visible_to_parent" type="checkbox" :id="`edit-session-visible-${s.session_id}`"
            class="rounded border-gray-300 text-primary-600 focus:ring-primary-500" />
          <label :for="`edit-session-visible-${s.session_id}`" class="text-xs text-gray-700">家長可見</label>
        </div>
        <div class="flex gap-2">
          <button @click="saveEdit(s.session_id)" :disabled="saving"
            class="bg-primary-600 hover:bg-primary-700 text-white rounded-lg px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50">
            {{ saving ? '儲存中...' : '儲存' }}
          </button>
          <button @click="cancelEdit"
            class="bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors">
            取消
          </button>
        </div>
      </div>

      <template v-else>
        <p class="text-sm text-gray-700"><span class="font-medium">內容：</span>{{ s.content_summary }}</p>
        <p v-if="s.homework" class="text-sm text-gray-600 bg-gray-50 rounded p-2 mt-1">
          <span class="font-medium">作業：</span>{{ s.homework }}
        </p>
        <p v-if="s.student_performance" class="text-sm text-gray-600 bg-gray-50 rounded p-2 mt-1">
          <span class="font-medium">表現：</span>{{ s.student_performance }}
        </p>
        <p v-if="s.next_plan" class="text-sm text-gray-600 bg-gray-50 rounded p-2 mt-1">
          <span class="font-medium">下次計畫：</span>{{ s.next_plan }}
        </p>
      </template>

      <!-- Edit history panel -->
      <Transition
        enter-active-class="transition duration-200 ease-out"
        enter-from-class="opacity-0 -translate-y-2"
        enter-to-class="opacity-100 translate-y-0"
        leave-active-class="transition duration-150 ease-in"
        leave-from-class="opacity-100 translate-y-0"
        leave-to-class="opacity-0 -translate-y-2">
        <div v-if="editLogOpen[s.session_id]" class="mt-2 ml-2 border-l-2 border-gray-200 pl-3">
          <p v-if="editLogLoading[s.session_id]" class="text-xs text-gray-400">載入修改紀錄...</p>
          <p v-else-if="editLogError[s.session_id]" class="text-xs text-red-500">{{ editLogError[s.session_id] }}</p>
          <div v-else-if="editLogs[s.session_id]?.length" class="space-y-2">
            <div v-for="log in editLogs[s.session_id]" :key="log.log_id"
              class="bg-gray-50 rounded p-2 text-xs text-gray-600">
              <div class="flex items-center gap-2 mb-1">
                <span class="font-medium text-gray-700">{{ fieldLabel(log.field_name) }}</span>
                <span class="text-gray-400">{{ formatDateTime(log.edited_at) }}</span>
              </div>
              <div class="flex gap-4">
                <span><span class="text-gray-400">舊：</span>{{ log.old_value ?? '(空)' }}</span>
                <span><span class="text-gray-400">新：</span>{{ log.new_value ?? '(空)' }}</span>
              </div>
            </div>
          </div>
          <p v-else class="text-xs text-gray-400">尚無修改紀錄</p>
        </div>
      </Transition>
    </div>
  </div>
  <p v-else class="text-gray-400 text-sm">尚無上課紀錄</p>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { sessionsApi } from '@/api/sessions'
import { useToastStore } from '@/stores/toast'

const toast = useToastStore()

defineProps({
  sessions: { type: Array, default: () => [] },
  showVisibility: { type: Boolean, default: false },
  editable: { type: Boolean, default: false },
})

const emit = defineEmits(['updated', 'deleted'])

const editLogOpen = reactive({})
const editLogLoading = reactive({})
const editLogError = reactive({})
const editLogs = reactive({})

const FIELD_LABELS = {
  session_date: '上課日期',
  hours: '時數',
  content_summary: '教學內容',
  homework: '作業',
  student_performance: '學生表現',
  next_plan: '下次計畫',
  visible_to_parent: '家長可見',
}

function fieldLabel(name) {
  return FIELD_LABELS[name] || name
}

async function toggleEditLogs(sessionId) {
  if (editLogOpen[sessionId]) {
    editLogOpen[sessionId] = false
    return
  }
  editLogOpen[sessionId] = true
  // Fetch only if not already loaded
  if (editLogs[sessionId]) return
  editLogLoading[sessionId] = true
  editLogError[sessionId] = ''
  try {
    const res = await sessionsApi.getEditLogs(sessionId)
    editLogs[sessionId] = res
  } catch (e) {
    editLogError[sessionId] = e.message || '載入失敗'
  } finally {
    editLogLoading[sessionId] = false
  }
}

// Inline edit
const editingSessionId = ref(null)
const saving = ref(false)
const editForm = reactive({
  session_date: '', hours: 2, content_summary: '',
  homework: '', student_performance: '', next_plan: '',
  visible_to_parent: true,
})

function startEdit(session) {
  editingSessionId.value = session.session_id
  editForm.session_date = String(session.session_date).slice(0, 10)
  editForm.hours = session.hours
  editForm.content_summary = session.content_summary || ''
  editForm.homework = session.homework || ''
  editForm.student_performance = session.student_performance || ''
  editForm.next_plan = session.next_plan || ''
  editForm.visible_to_parent = !!session.visible_to_parent
}

function cancelEdit() {
  editingSessionId.value = null
}

async function saveEdit(sessionId) {
  saving.value = true
  try {
    await sessionsApi.update(sessionId, {
      session_date: editForm.session_date,
      hours: editForm.hours,
      content_summary: editForm.content_summary,
      homework: editForm.homework || null,
      student_performance: editForm.student_performance || null,
      next_plan: editForm.next_plan || null,
      visible_to_parent: editForm.visible_to_parent,
    })
    editingSessionId.value = null
    emit('updated')
  } catch (e) {
    toast.error(e.message || '更新失敗')
  } finally {
    saving.value = false
  }
}

async function confirmDelete(sessionId) {
  if (!window.confirm('確定要刪除此上課紀錄嗎？此操作無法復原。')) return
  try {
    await sessionsApi.delete(sessionId)
    emit('deleted')
  } catch (e) {
    toast.error(e.message || '刪除失敗')
  }
}

function getTimezoneAbbr() {
  try {
    return Intl.DateTimeFormat('zh-TW', { timeZoneName: 'short' })
      .formatToParts(new Date())
      .find(p => p.type === 'timeZoneName')?.value || ''
  } catch {
    return ''
  }
}

const tzAbbr = getTimezoneAbbr()

function formatDate(dt) {
  if (!dt) return ''
  const dateStr = new Date(dt).toLocaleDateString('zh-TW')
  return tzAbbr ? `${dateStr} (${tzAbbr})` : dateStr
}

function formatDateTime(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleString('zh-TW', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
    timeZoneName: 'short',
  })
}
</script>
