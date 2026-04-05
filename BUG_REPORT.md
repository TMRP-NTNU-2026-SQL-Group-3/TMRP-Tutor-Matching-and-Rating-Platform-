# TMRP 全面 Bug 審查報告與修復方案

> 審查日期：2026-04-05
> 涵蓋範圍：`tutor-platform-api/`（FastAPI 後端）＋ `tutor-platform-web/src/`（Vue 3 前端）
> Bug 總數：63 項（Critical 5 / High 9 / Medium 27 / Low 22）

---

## 目錄

- [一、CRITICAL — 立即修復](#一critical--立即修復)
- [二、HIGH — 本週修復](#二high--本週修復)
- [三、MEDIUM — 排入迭代](#三medium--排入迭代)
- [四、LOW — 放入 Backlog](#四low--放入-backlog)

---

## 一、CRITICAL — 立即修復

### C1　SQL Injection：Repository 動態 UPDATE 欄位名未驗證

| 項目 | 內容 |
|------|------|
| 檔案 | `app/repositories/exam_repo.py:49-55`、`student_repo.py:27-33`、`review_repo.py:92-99`、`session_repo.py:70-77` |
| 問題 | `updates` dict 的 key 直接 f-string 插入 SQL `SET {col} = ?`，若 key 含惡意字串可注入 SQL |
| 嚴重度 | Critical |

**修復方式 — 在 `BaseRepository` 新增欄位白名單驗證：**

```python
# app/repositories/base.py — 新增方法

import re

_SAFE_COLUMN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

class BaseRepository:
    # ... 原有方法保留 ...

    @staticmethod
    def validate_columns(columns: list[str], allowed: set[str] | None = None) -> None:
        """驗證欄位名稱僅含合法識別字元，並可選擇限制於白名單。"""
        for col in columns:
            if not _SAFE_COLUMN.match(col):
                raise ValueError(f"不合法的欄位名稱：{col!r}")
            if allowed and col not in allowed:
                raise ValueError(f"不允許更新的欄位：{col!r}")

    def safe_update(self, table: str, id_col: str, id_val, updates: dict,
                    allowed_columns: set[str], extra_set: str = "") -> None:
        """安全的動態 UPDATE，強制驗證欄位白名單。"""
        self.validate_columns(list(updates.keys()), allowed_columns)
        set_clause = ", ".join(f"{col} = ?" for col in updates)
        if extra_set:
            set_clause += ", " + extra_set
        values = list(updates.values()) + [id_val]
        self.execute(
            f"UPDATE {table} SET {set_clause} WHERE {id_col} = ?",
            values,
        )
```

然後在各 Repository 改用：

```python
# app/repositories/exam_repo.py
ALLOWED_EXAM_COLUMNS = {"exam_date", "exam_type", "score", "visible_to_parent"}

def update(self, exam_id: int, updates: dict) -> None:
    self.safe_update("Exams", "exam_id", exam_id, updates, ALLOWED_EXAM_COLUMNS)

# app/repositories/student_repo.py
ALLOWED_STUDENT_COLUMNS = {"name", "school", "grade"}

def update(self, student_id: int, updates: dict) -> None:
    self.safe_update("Students", "student_id", student_id, updates, ALLOWED_STUDENT_COLUMNS)

# app/repositories/review_repo.py
ALLOWED_REVIEW_COLUMNS = {"rating_1", "rating_2", "rating_3", "rating_4",
                          "personality_comment", "comment"}

def update(self, review_id: int, updates: dict) -> None:
    self.safe_update("Reviews", "review_id", review_id, updates,
                     ALLOWED_REVIEW_COLUMNS, extra_set="updated_at = Now()")

# app/repositories/session_repo.py
ALLOWED_SESSION_COLUMNS = {"session_date", "hours", "content_summary", "homework",
                           "student_performance", "next_plan", "visible_to_parent"}

def update(self, session_id: int, fields: dict) -> None:
    self.safe_update("Sessions", "session_id", session_id, fields,
                     ALLOWED_SESSION_COLUMNS, extra_set="updated_at = Now()")
```

---

### C2　SQL Injection：CSV 匯入欄位名未驗證

| 項目 | 內容 |
|------|------|
| 檔案 | `app/tasks/import_export.py:34-37` |
| 問題 | CSV header 直接插入 `INSERT INTO ... ({col_names})`，table 有白名單但 column 沒有 |
| 嚴重度 | Critical |

**修復方式 — 加入欄位名稱正規驗證：**

```python
# app/tasks/import_export.py — 在 import_csv_task 內，columns = list(...) 之後加���：

import re
_SAFE_COLUMN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

# ... 在 columns = list(rows[0].keys()) 之後：
for col in columns:
    if not _SAFE_COLUMN.match(col):
        return {"table": table_name, "error": f"不合法的欄位名稱：{col!r}"}
```

---

### C3　硬編碼 JWT Secret

| 項目 | 內容 |
|------|------|
| 檔案 | `app/config.py:9` |
| 問題 | `jwt_secret_key` 預設為 `"change-me-in-production"`，無啟動檢查 |
| 嚴重度 | Critical |

**修復方式 — 在 `main.py` 啟動時檢查：**

```python
# app/main.py — startup_event 中加入：

@app.on_event("startup")
async def startup_event():
    if settings.jwt_secret_key == "change-me-in-production":
        logger.warning(
            "⚠️ JWT_SECRET_KEY 使用預設值！請在 .env 中設定安全的密鑰。"
            "正式環境務必更換，否則任何人都能偽造 Token。"
        )
    # ... 其餘不變
```

建議同時在 `.env.example` 中標注此欄位必填。

---

### C4　硬編碼管理員帳密

| 項目 | 內容 |
|------|------|
| 檔案 | `app/config.py:13-14` |
| 問題 | `admin/admin123` 為預設管理員帳密，可被任何人登入 |
| 嚴重度 | Critical |

**修復方式 — 啟動時同步警告 + 強制從環境變數讀取：**

```python
# app/main.py — startup_event 中加入：

    if settings.admin_password == "admin123":
        logger.warning(
            "⚠️ ADMIN_PASSWORD 使用預設值！請在 .env 中設定強密碼。"
        )
```

正式部署前必須在 `.env` 設定 `ADMIN_PASSWORD=<隨機強密碼>`。

---

### C5　SQL Wildcard Injection

| 項目 | 內容 |
|------|------|
| 檔案 | `app/repositories/tutor_repo.py:31-32` |
| 問題 | `school` 參數中的 `%` `_` 字元未跳脫，可造成 LIKE wildcard injection |
| 嚴重度 | Critical |

**修復方式 — 跳脫 LIKE 萬用字元：**

```python
# app/repositories/tutor_repo.py — search() 中修改：

if school:
    # 跳脫 LIKE 萬用字元
    escaped = school.replace("%", "[%]").replace("_", "[_]")
    conditions.append("t.university LIKE ?")
    params.append(f"%{escaped}%")
```

---

## 二、HIGH — 本週修復

### H1　Auth Store Token/User 不同步

| 項目 | 內容 |
|------|------|
| 檔案 | `src/stores/auth.js:5-12` |
| 問題 | localStorage `token` 存在但 `user` 被破壞時，`isLoggedIn=true` 但 `user=null`，所有存取 `auth.user.xxx` 的地方會爆炸 |
| 嚴重度 | High |

**修復方式 — `isLoggedIn` 同時檢查 token 和 user：**

```javascript
// src/stores/auth.js
const isLoggedIn = computed(() => !!token.value && !!user.value)
```

---

### H2　SessionForm 日期時區偏移

| 項目 | 內容 |
|------|------|
| 檔案 | `src/components/session/SessionForm.vue:86` |
| 問題 | `new Date(form.session_date).toISOString()` 將 date-only 值強制 UTC 轉換，可能偏移 ±1 天 |
| 嚴重度 | High |

**修復方式 — 直接傳遞 date string，不經 Date 轉換：**

```javascript
// src/components/session/SessionForm.vue — handleSubmit 內：
emit('submit', {
  session_date: form.session_date,  // 直接傳 "YYYY-MM-DD"，不轉 ISO
  hours: form.hours,
  // ... 其餘不變
})
```

---

### H3　AvailabilityCalendar 顯示 NaN:NaN

| 項目 | 內容 |
|------|------|
| 檔案 | `src/components/tutor/AvailabilityCalendar.vue:21-24` |
| 問題 | `new Date("14:00")` → Invalid Date → `getHours()` 回傳 NaN |
| 嚴重度 | High |

**修復方式 — 改用字串解析：**

```javascript
// src/components/tutor/AvailabilityCalendar.vue
function formatTime(dt) {
  if (!dt) return ''
  // 若已是 "HH:MM" 或 "HH:MM:SS" 格式，直接截取
  if (typeof dt === 'string' && /^\d{2}:\d{2}/.test(dt)) {
    return dt.slice(0, 5)
  }
  // 若為完整日期時間字串，才使用 Date 解析
  const d = new Date(dt)
  if (isNaN(d.getTime())) return dt  // fallback: 原值
  return d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0')
}
```

---

### H4��Response Interceptor 假設固定回應格式

| 項目 | 內容 |
|------|------|
| 檔案 | `src/api/index.js:19-26` |
| 問題 | 若後端回傳格式不符 `{success, data, message}`，`success` 為 `undefined`，觸發 `!success` 錯誤 |
| 嚴重度 | High |

**修復方式 — 加入防禦性檢查：**

```javascript
// src/api/index.js — response interceptor
api.interceptors.response.use(
  response => {
    const body = response.data
    // 若回應非標準格式（例如直接下載），直接回傳
    if (body === undefined || body === null || typeof body !== 'object' || !('success' in body)) {
      return body
    }
    const { success, data, message } = body
    if (!success) {
      return Promise.reject(new Error(message || '操作失敗'))
    }
    return data
  },
  // ... error handler 不變
)
```

---

### H5　BaseRepository Cursor 未關閉

| 項目 | 內容 |
|------|------|
| 檔案 | `app/repositories/base.py:4-6` |
| 問題 | `__init__` 建立 cursor 但無 `close()` 機制，造成資源洩漏 |
| 嚴重度 | High |

**修復方式 — 加入 `close()` 方法並在 `get_db` 中清理：**

```python
# app/repositories/base.py
class BaseRepository:
    def __init__(self, conn):
        self.conn = conn
        self.cursor = conn.cursor()

    def close(self):
        """關閉 cursor（connection 由外層管理）。"""
        try:
            self.cursor.close()
        except Exception:
            pass
```

由於 cursor 生命週期與 connection 相同（FastAPI `get_db` dependency 管理 conn），cursor 會隨 conn.close() 一起釋放。此修復為防禦性措施。

---

### H6���CSV 匯入失敗時未 Rollback

| 項目 | 內容 |
|------|------|
| 檔案 | `app/tasks/import_export.py:38-49` |
| 問題 | except 區塊只記 log，未呼叫 `conn.rollback()`，部分資料可能隨 `conn.close()` 自動 commit |
| 嚴重度 | High |

**修復方式 — except 中加入 rollback：**

```python
# app/tasks/import_export.py — import_csv_task

    except Exception as e:
        conn.rollback()  # ← 新增
        logger.error("匯入 %s 失敗: %s", table_name, str(e))
        return {"table": table_name, "error": str(e)}
    finally:
        conn.close()
```

---

### H7　Scheduled Task 使用無效的 MS Access Boolean

| 項目 | 內容 |
|------|------|
| 檔案 | `app/tasks/scheduled.py:19-20, 35-36` |
| 問題 | SQL 中使用 Python `True`/`False`，MS Access 不認識；應用 `0`/`-1` |
| 嚴重度 | High |

**修復方式 — 使用 `to_access_bit`：**

```python
# app/tasks/scheduled.py
from app.utils.access_bits import to_access_bit

def _ensure_is_locked_column(conn) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT TOP 1 is_locked FROM Reviews")
    except Exception:
        cursor.execute("ALTER TABLE Reviews ADD COLUMN is_locked BIT")
        cursor.execute("UPDATE Reviews SET is_locked = ?", (to_access_bit(False),))
        conn.commit()
        logger.info("已新增 is_locked 欄位至 Reviews")

# check_expired_reviews 內：
        cursor.execute(
            "UPDATE Reviews SET is_locked = ? "
            "WHERE created_at < ? AND (is_locked = ? OR is_locked IS NULL)",
            (to_access_bit(True), cutoff, to_access_bit(False)),
        )
```

---

### H8　可對未開始的配對提交評價

| 項目 | 內容 |
|------|------|
| 檔案 | `app/routers/reviews.py:26-28` |
| 問題 | `create_review` 未檢查 `match.status`，可對 `pending`/`cancelled`/`rejected` 配對提交評價，污染評分資料 |
| 嚴重度 | High |

**修復方式 — 加入 status 檢查：**

```python
# app/routers/reviews.py — create_review 中，在 match = repo.get_match_for_create(...) 之後加入：

    REVIEWABLE_STATUSES = {'active', 'paused', 'terminating', 'ended'}
    if match["status"] not in REVIEWABLE_STATUSES:
        raise AppException("只能對進行中或已結束的配對提交評價")
```

---

### H9　termination_reason 夾帶 status 前綴洩漏至前端

| 項目 | 內容 |
|------|------|
| 檔案 | `app/repositories/match_repo.py:75-83` |
| 問題 | `set_terminating` 存入 `f"{previous_status}|{reason}"`，但 `find_by_id` 用 `SELECT *` 回傳原始值，前端 `displayReason` 雖有做 split 但不應讓原始值流出 |
| 嚴重度 | High |

**修復方式 — 使用獨立欄位存 `previous_status`，或在 API 層清洗：**

方案 A（最小改動）— 在 `routers/matches.py` `get_match_detail` 回傳前清洗：

```python
# app/routers/matches.py — get_match_detail 中，return 之前：

    # 清洗 termination_reason，只回傳使用者可見的原因
    raw_reason = match.get("termination_reason") or ""
    if "|" in raw_reason:
        match["termination_reason"] = raw_reason.split("|", 1)[1]
```

方案 B（更乾淨）— 新增 `previous_status` 欄位到 Matches 表，分開儲存。

---

## 三、MEDIUM — 排入迭代

### M1　Router 缺少 404 Catch-all

| 項目 | 內容 |
|------|------|
| 檔案 | `src/router/index.js:4-64` |
| 問題 | 無 `/:pathMatch(.*)*` 路由，未知 URL 顯示空白頁 |

**修復方式：**

```javascript
// src/router/index.js — routes 陣列最後加入：
  { path: '/:pathMatch(.*)*', redirect: '/login' },
```

---

### M2　ConversationListView 錯誤被吞

| 項目 | 內容 |
|------|------|
| 檔案 | `src/views/messages/ConversationListView.vue:49` |
| 問題 | API 失敗只 `console.error`，使用者看到「尚無對話」而非錯誤訊息 |

**修復方式：**

```javascript
// src/views/messages/ConversationListView.vue
const error = ref('')

onMounted(async () => {
  loading.value = true
  try {
    conversations.value = await messagesApi.listConversations()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})
```

template 中加入：
```html
<p v-if="error" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ error }}</p>
```

---

### M3　ExpenseView / IncomeView：null 值 crash

| 項目 | 內容 |
|------|------|
| 檔案 | `src/views/parent/ExpenseView.vue:19`、`src/views/tutor/IncomeView.vue:19` |
| 問題 | `data.total_expense.toLocaleString()` 若值為 null 會 TypeError |

**修復方式：**

```html
<!-- ExpenseView.vue:19 -->
NT$ {{ (data.total_expense ?? 0).toLocaleString() }}

<!-- IncomeView.vue:19 -->
NT$ {{ (data.total_income ?? 0).toLocaleString() }}
```

同理在 breakdown 的 `row.expense.toLocaleString()` 和 `row.income.toLocaleString()` 也加 `?? 0`。

---

### M4　TutorDetailView 錯誤顯示為「找不到老師」

| 項目 | 內容 |
|------|------|
| 檔案 | `src/views/parent/TutorDetailView.vue:160-170` |
| 問題 | API 失敗時 `tutor` 仍為 null，顯示 EmptyState「找不到此老師」而非錯誤 |

**修復方式：**

```javascript
// src/views/parent/TutorDetailView.vue
const error = ref('')

onMounted(async () => {
  loading.value = true
  try {
    // ...
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})
```

template 中 `<EmptyState v-else ...>` 改為：
```html
<div v-else>
  <p v-if="error" class="text-sm text-danger bg-red-50 rounded-lg p-3">{{ error }}</p>
  <EmptyState v-else message="找不到此老師" />
</div>
```

---

### M5　canReview 的 status 可能與後端不一致

| 項目 | 內容 |
|------|------|
| 檔案 | `src/views/parent/MatchDetailView.vue:222-228` |
| 問題 | 前端檢查 `'ended'` 但後端狀態機中也有 `'terminating'`、`'paused'` 等可評價狀態 |

**修復方式 — 與 H8 的後端修復保持一致：**

```javascript
const canReview = computed(() =>
  ['active', 'paused', 'terminating', 'ended'].includes(match.value?.status)
)
```

---

### M6　ProfileView 非原子性儲存

| 項目 | 內容 |
|------|------|
| 檔案 | `src/views/tutor/ProfileView.vue:142-158` |
| 問題 | `updateProfile` 成功但 `updateSubjects` 失敗，使用者只看到錯誤，不知道 profile 已部分儲存 |

**修復方式 — 提供更清楚的錯誤提示：**

```javascript
async function handleSave() {
  error.value = ''
  success.value = ''
  saving.value = true
  try {
    await tutorsApi.updateProfile(form)

    const validSubjects = subjectList.value.filter(s => s.subject_id && s.hourly_rate)
    try {
      await tutorsApi.updateSubjects({ subjects: validSubjects })
    } catch (e) {
      error.value = '基本資料已儲存，但科目設定失敗：' + e.message
      return
    }

    success.value = '個人檔案已更新'
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}
```

---

### M7　RegisterView 無防重複提交

| 項目 | 內容 |
|------|------|
| 檔案 | `src/views/RegisterView.vue:46-49` |
| 問題 | 無 loading/disabled 狀態，連續點擊可建立重複帳號 |

**修復方式：**

```javascript
// <script setup> 中加入：
const submitting = ref(false)

async function handleRegister() {
  if (submitting.value) return
  submitting.value = true
  try {
    error.value = ''
    await authApi.register(form)
    router.push('/login')
  } catch (e) {
    error.value = e.message
  } finally {
    submitting.value = false
  }
}
```

template button 加 `:disabled="submitting"`。

---

### M8　ContractForm 未重設

| 項目 | 內容 |
|------|------|
| 檔案 | `src/components/match/ContractForm.vue:38` |
| 問題 | 提交後 `reason` ref 未清空，重新開啟表單仍顯示舊文字 |

**修復方式：**

```javascript
// src/components/match/ContractForm.vue — 加入 reset 並 expose

function reset() {
  reason.value = ''
}

defineExpose({ reset })
```

父元件在 submit 後呼叫 `contractFormRef.value.reset()`。

---

### M9　InviteForm 無前端驗證

| 項目 | 內容 |
|------|------|
| 檔案 | `src/components/match/InviteForm.vue:55` |
| 問題 | `@click="$emit('submit', { ...form })"` 未檢查必填欄位 |

**修復方式 — 改為呼叫 method：**

```javascript
function handleSubmit() {
  if (!form.student_id || !form.subject_id || !form.hourly_rate) return
  emit('submit', { ...form })
}
```

template 中 `@click="$emit('submit', { ...form })"` 改為 `@click="handleSubmit"`。

---

### M10　InviteForm 提交後未重設

| 項目 | 內容 |
|------|------|
| 檔案 | `src/components/match/InviteForm.vue:81-88` |

**修復方式：**

```javascript
function reset() {
  form.student_id = null
  form.subject_id = null
  form.hourly_rate = 0
  form.sessions_per_week = 1
  form.want_trial = false
  form.invite_message = ''
}

defineExpose({ reset })
```

---

### M11　SessionForm reset() 不完整

| 項目 | 內容 |
|------|------|
| 檔案 | `src/components/session/SessionForm.vue:96-102` |
| 問題 | `reset()` 未重設 `hours`（預設 2）和 `visible_to_parent`（預設 false） |

**修復方式：**

```javascript
function reset() {
  form.session_date = ''
  form.hours = 2           // ← 新增
  form.content_summary = ''
  form.homework = ''
  form.student_performance = ''
  form.next_plan = ''
  form.visible_to_parent = false  // ← 新增
}
```

---

### M12　ReviewForm review_type 不隨 prop 更新

| 項目 | 內容 |
|------|------|
| 檔案 | `src/components/review/ReviewForm.vue:81` |
| 問題 | `form.review_type` 僅在 reactive 初始化時讀取 `props.reviewTypes[0]?.value`，若 prop 後續才載入，值為 undefined |

**修復方式 — 加入 watch：**

```javascript
import { reactive, computed, watch } from 'vue'

// 在 form 定義之後加入：
watch(
  () => props.reviewTypes,
  (types) => {
    if (types.length && !form.review_type) {
      form.review_type = types[0].value
    }
  },
  { immediate: true }
)
```

---

### M13　ProgressChart X 軸未按日期排序

| 項目 | 內容 |
|------|------|
| 檔案 | `src/components/stats/ProgressChart.vue:48-51` |
| 問題 | `allDates` 用 Set 保留插入順序，未按時間排序 |

**修復方式：**

```javascript
// src/components/stats/ProgressChart.vue — chartData computed 內：

  // 取得所有不重複日期作為 x 軸��並按時間排序
  const allDates = [...new Set(props.exams.map(e => {
    const d = new Date(e.exam_date)
    return d.toLocaleDateString('zh-TW')
  }))].sort((a, b) => new Date(a) - new Date(b))
```

注意：中文 locale 日期可能排序有問題，更穩定的做法是先用 ISO 格式排序再轉顯示格式。

---

### M14　useMatchDetail null dereference

| 項目 | 內容 |
|------|------|
| 檔案 | `src/composables/useMatchDetail.js:64, 79` |
| 問題 | `match.value.match_id` 在 `match.value` 為 null 時 crash |

**修復方式：**

```javascript
async function doAction(action) {
  if (!match.value) return  // ← 新增
  // ...
}

async function doTerminate(reason) {
  if (!match.value) return  // ← 新增
  // ...
}
```

---

### M15　搜尋排序��漏「隱藏時薪」老師

| 項目 | 內容 |
|------|------|
| 檔案 | `app/routers/tutors.py:80-91` |
| 問題 | `show_hourly_rate=False` 的老師在 `rate_asc` 排序中算 0，排最前面 |

**修復方式 — 隱藏時薪的老師不參與費率排序：**

```python
# app/routers/tutors.py — 排序區塊改為：

if sort_by == "rate_asc":
    results.sort(key=lambda x: (
        0 if any(s.get("hourly_rate") for s in x.get("subjects", [])) else 1,  # 無費率排最後
        sum(s["hourly_rate"] for s in x.get("subjects", []) if s.get("hourly_rate")) or float('inf')
    ))
```

---

### M16　send_message INSERT + UPDATE 非原子

| 項目 | 內容 |
|------|------|
| 檔案 | `app/repositories/message_repo.py:57-67` |
| 問題 | INSERT 和 UPDATE `last_message_at` 分兩次 commit，中間可讀到不一致狀態 |

**修復方式 — 合併為單一 commit：**

```python
def send_message(self, conversation_id: int, sender_user_id: int, content: str) -> int:
    sql = """
        INSERT INTO Messages (conversation_id, sender_user_id, content, sent_at)
        VALUES (?, ?, ?, Now())
    """
    self.cursor.execute(sql, (conversation_id, sender_user_id, content))
    self.cursor.execute("SELECT @@IDENTITY")
    msg_id = self.cursor.fetchone()[0]

    self.cursor.execute(
        "UPDATE Conversations SET last_message_at = Now() WHERE conversation_id = ?",
        (conversation_id,),
    )
    self.conn.commit()  # 一次 commit
    return msg_id
```

---

### M17　replace_subjects / replace_availability 無 rollback

| 項目 | 內容 |
|------|------|
| 檔案 | `app/repositories/tutor_repo.py:90-113` |
| 問題 | DELETE 後 INSERT 失敗，tutor 丟失所有科目，無 rollback |

**修復方式 — 加入 try/except rollback：**

```python
def replace_subjects(self, tutor_id: int, items: list[dict]) -> None:
    try:
        self.cursor.execute("DELETE FROM Tutor_Subjects WHERE tutor_id = ?", (tutor_id,))
        for item in items:
            self.cursor.execute(
                "INSERT INTO Tutor_Subjects (tutor_id, subject_id, hourly_rate) VALUES (?, ?, ?)",
                (tutor_id, item["subject_id"], item["hourly_rate"]),
            )
        self.conn.commit()
    except Exception:
        self.conn.rollback()
        raise
```

`replace_availability` 同理。

---

### M18　Logger 重複添加 Handler

| 項目 | 內容 |
|------|------|
| 檔案 | `app/utils/logger.py:25-28` |
| 問題 | 每次呼叫 `setup_logger()` 都新增 handler，導致重複 log |

**修復方式：**

```python
def setup_logger() -> logging.Logger:
    root_logger = logging.getLogger("app")
    if root_logger.handlers:  # ← 已初始化，直接返回
        return root_logger
    # ... 其餘不變
```

---

### M19　stats_tasks 月份解析未驗證

| 項目 | 內容 |
|------|------|
| 檔案 | `app/tasks/stats_tasks.py:23-24, 59-60` |
| 問題 | `month.split("-")` 無格式驗證，錯誤格式會 crash 且洩漏 traceback |

**修復方式：**

```python
# 在 calculate_income_stats 和 calculate_expense_stats 中：

if month:
    try:
        year, mon = map(int, month.split("-"))
        if not (1 <= mon <= 12):
            return {"error": "無效的月份值"}
    except (ValueError, TypeError):
        return {"error": "月份格式應為 YYYY-MM"}
```

---

### M20　Worker 忽略 config 設定

| 項目 | 內容 |
|------|------|
| 檔案 | `app/worker.py:3` |
| 問題 | 硬寫 `"data/huey.db"` 而非讀取 `settings.huey_db_path` |

**修復方式：**

```python
# app/worker.py
from app.config import settings
from huey import SqliteHuey

huey = SqliteHuey(filename=settings.huey_db_path)
```

---

### M21　export_csv 未建立匯出目錄

| 項目 | 內容 |
|------|------|
| 檔案 | `app/routers/admin.py:146-148` |
| 問題 | `export_csv` 未呼叫 `mkdir()`，首次呼叫時 crash |

**修復方式：**

```python
# app/routers/admin.py — export_csv 中，export_dir 之後加入：
    export_dir = Path("data/export")
    export_dir.mkdir(parents=True, exist_ok=True)  # ← 新增
    export_path = export_dir / f"{table_name}.csv"
```

---

### M22　搜尋老師 N+1 查詢 + 無分頁

| 項目 | 內容 |
|------|------|
| 檔案 | `app/routers/tutors.py:51-97` |
| 問題 | 每位老師各查 `get_subjects` + `get_avg_rating`，100 位老師 = 200+ 查詢 |

**修復方式（短期）— 加入分頁：**

```python
@router.get("", ...)
def search_tutors(
    # ... 原有參數 ...
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    # ...
):
    # ... 原有邏輯 ...
    # 在排序完成後加入分頁
    total = len(results)
    start = (page - 1) * page_size
    paginated = results[start:start + page_size]
    return ApiResponse(success=True, data={"items": paginated, "total": total})
```

長期應考慮用 SQL JOIN 一次查完。

---

### M23　reset_database 非原子

| 項目 | 內容 |
|------|------|
| 檔案 | `app/routers/admin.py:172-183` |
| 問題 | 每張表單獨 commit，中途失敗留下殘缺資料 |

**修復方式 — 手動控制 transaction：**

```python
def reset_database(...):
    # ...
    cursor = conn.cursor()
    deleted = {}
    try:
        for table in _DELETE_ORDER:
            if table == "Users":
                rows_before = repo.fetch_one(f"SELECT COUNT(*) AS cnt FROM {table}")
                cursor.execute(f"DELETE FROM {table} WHERE user_id <> ?", (admin_user_id,))
                rows_after = repo.fetch_one(f"SELECT COUNT(*) AS cnt FROM {table}")
                deleted[table] = (rows_before["cnt"] or 0) - (rows_after["cnt"] or 0)
            else:
                rows = repo.fetch_one(f"SELECT COUNT(*) AS cnt FROM {table}")
                cursor.execute(f"DELETE FROM {table}")
                deleted[table] = rows["cnt"] or 0
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    # ...
```

---

### M24　CSV 匯入值全為字串

| 項目 | 內容 |
|------|------|
| 檔案 | `app/routers/admin.py:117-121` |
| 問題 | `csv.DictReader` 的值全為 `str`，BIT/INT 欄位可能匯入失敗 |

**修復方式 — 讓 ODBC driver 做型別轉換（通常已可處理）。若需更精確：**

```python
# 對 boolean 欄位做轉換（可選）
def _coerce_value(val):
    if val in ('True', 'true', '1', '-1'):
        return -1  # MS Access BIT True
    if val in ('False', 'false', '0'):
        return 0
    return val
```

---

### M25　pickle.loads 反序列化風險

| 項目 | 內容 |
|------|------|
| 檔案 | `app/routers/admin.py:273-276` |
| 問題 | `pickle.loads(raw)` 可執行任意程式碼 |

**修復方式 — 由於這是 Huey 內部格式，短期內包在 try/except 中即可。長期可考慮改用 JSON storage。目前已限 admin-only，風險可接受但應加註記：**

```python
# 加上安全註解
import pickle  # nosec B301 — admin-only, data from local Huey SQLite storage
```

---

### M26　update_status 無狀態轉換驗證

| 項目 | 內容 |
|------|------|
| 檔案 | `app/repositories/match_repo.py:71-73` |
| 問題 | 接受任意 status 字串 |

**修復方式 — 此驗證已在 router 層的 TRANSITIONS dict 完成，repository 層屬於信任的內部呼叫。此為 Low 風險。可選擇加入 assertion：**

```python
VALID_STATUSES = {'pending', 'trial', 'active', 'paused', 'cancelled',
                  'rejected', 'terminating', 'ended'}

def update_status(self, match_id: int, new_status: str) -> None:
    assert new_status in VALID_STATUSES, f"Invalid status: {new_status}"
    sql = "UPDATE Matches SET status = ?, updated_at = Now() WHERE match_id = ?"
    self.execute(sql, (new_status, match_id))
```

---

### M27　csv_handler 無路徑遍歷保護

| 項目 | 內容 |
|------|------|
| 檔案 | `app/utils/csv_handler.py:5-10` |
| 問題 | `read_csv` 接受任意路徑，可能讀取系統檔案 |

**修復方式 — 限制在 data 目錄下：**

```python
def read_csv(file_path: str) -> list[dict]:
    path = Path(file_path).resolve()
    allowed_base = Path("data").resolve()
    if not str(path).startswith(str(allowed_base)):
        raise ValueError(f"不允許的檔案路徑：{file_path}")
    with path.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)
```

---

## 四、LOW — 放入 Backlog

### L1　ChatView 初始載入雙重 fetch

| 檔案 | `src/views/messages/ChatView.vue:125-139` |
|------|------|
| 問題 | `onMounted` 和 `watch(route.params.id)` 同時觸發 |

**修復：** watch 加 `{ immediate: false }`（已預設，但確認 onMounted 不與 watch 重疊），或將 onMounted 邏輯移入 watch 加 `immediate: true`：

```javascript
watch(() => route.params.id, async () => {
  loading.value = true
  error.value = ''
  messages.value = []
  await fetchMessages()
  loading.value = false
  startPolling()
}, { immediate: true })

// 刪除 onMounted 中的相同邏輯
```

---

### L2　TutorDetailView 使用 alert() 而非 toast

| 檔案 | `src/views/parent/TutorDetailView.vue:134, 151` |
|------|------|

**修復：**
```javascript
import { useToastStore } from '@/stores/toast'
const toast = useToastStore()

// 134 行：alert(e.message) → toast.error(e.message)
// 151 行：alert('邀請已送出！') → toast.success('邀請已送出！')
```

---

### L3　Tutor MatchDetailView 考試表單未完全重設

| 檔案 | `src/views/tutor/MatchDetailView.vue:395-398` |
|------|------|
| 問題 | `exam_type` 和 `visible_to_parent` 未重設 |

**修復：** 在重設區塊加入：
```javascript
examForm.exam_type = '段考'
examForm.visible_to_parent = false
```

---

### L4　`/` 路由雙重重導

| 檔案 | `src/router/index.js:63` |
|------|------|

**修復：**
```javascript
{
  path: '/',
  redirect: () => {
    const auth = useAuthStore()
    if (!auth.isLoggedIn) return '/login'
    if (auth.role === 'admin') return '/admin'
    if (auth.role === 'tutor') return '/tutor'
    return '/parent'
  }
},
```

---

### L5　LoginView 無 loading 狀態

| 檔案 | `src/views/LoginView.vue:50-64` |
|------|------|

**修復：** 加入 `const submitting = ref(false)`，在 `handleLogin` 中設定，button 加 `:disabled="submitting || !username || !password"`。

---

### L6　ProgressChart 同日同科目成績覆蓋

| 檔案 | `src/components/stats/ProgressChart.vue:58` |
|------|------|

**修復：** 改用陣列存儲同日成績，取平均：
```javascript
if (!dataMap[label]) dataMap[label] = []
dataMap[label].push(e.score)
// ...
data: allDates.map(d => {
  const arr = dataMap[d]
  return arr ? arr.reduce((a, b) => a + b, 0) / arr.length : null
})
```

---

### L7　ProgressChart tooltip 顯示 null

| 檔案 | `src/components/stats/ProgressChart.vue:80-82` |
|------|------|

**修復：**
```javascript
callbacks: {
  label: (ctx) => ctx.raw != null ? `${ctx.dataset.label}：${ctx.raw} 分` : null,
}
```

---

### L8　RadarChart tooltip crash on null

| 檔案 | `src/components/review/RadarChart.vue:66` |
|------|------|

**修復：**
```javascript
label: (ctx) => `${ctx.label}：${(ctx.raw ?? 0).toFixed(1)}`,
```

---

### L9　matchesApi.updateStatus 過濾空字串 reason

| 檔案 | `src/api/matches.js:14-15` |
|------|------|

**修復：** 將 `if (reason)` 改為 `if (reason != null)`，讓空字串也能傳遞。

---

### L10　AppNav auth prop 形狀未定義

| 檔案 | `src/components/common/AppNav.vue:79` |
|------|------|

**修復：** 明確定義 prop 形狀：
```javascript
defineProps({
  auth: {
    type: Object,
    required: true,
    // 預期：{ role: string, user: { display_name: string } }
  },
})
```

---

### L11　fetch_paginated 全量載入

| 檔案 | `app/repositories/base.py:37-50` |
|------|------|
| 問題 | MS Access 不支援 LIMIT/OFFSET，目前做法為已知限制 |

**修復：** 短期保持現狀（已有註解說明原因）。長期若遷移至支援 LIMIT 的資料庫再優化。

---

### L12　Tutor model 時間欄位型別不符

| 檔案 | `app/models/tutor.py:27-30` |
|------|------|

**修復：** 若 DB 存的是 DATETIME，model 可改為 `str` 並加格式驗證：
```python
start_time: str = Field(..., pattern=r'^\d{2}:\d{2}(:\d{2})?$')
```

---

### L13　decode_access_token 吞掉所有 JWT 錯誤

| 檔案 | `app/utils/security.py:29-34` |
|------|------|

**修復：**
```python
import logging
logger = logging.getLogger("app.security")

def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        logger.warning("JWT decode failed: %s", type(e).__name__)
        return None
```

---

### L14　Seed data termination_reason 格式不一致

| 檔案 | `seed/generator.py:382` |
|------|------|

**修復：** 將 seed 中的 `termination_reason` 改為與 `set_terminating` 相同格式：
```python
"termination_reason": "active|學生搬家，不方便繼續上課",
```

---

### L15　CSV 匯出使用相對路徑

| 檔案 | `app/tasks/import_export.py:69` |
|------|------|

**修復：** 使用 config 的基礎路徑：
```python
from app.config import settings
export_dir = Path(settings.access_db_path).parent / "export"
```

---

### L16　test_auth.py 錯誤的 HTTP status

| 檔案 | `tests/test_auth.py:169-171` |
|------|------|
| 問題 | 無 Token 應回 401，但 FastAPI `HTTPBearer` 預設回 403 |

**修復：** 若要修正語義，自訂 bearer scheme：
```python
# app/dependencies.py
security_scheme = HTTPBearer(auto_error=False)

def get_current_user(credentials = Depends(security_scheme)):
    if credentials is None:
        raise HTTPException(status_code=401, detail="未提供認證 Token")
    # ...
```

並將 test 中的 `assert resp.status_code == 403` 改為 `401`。

---

### L17　Admin 存取 list_matches 回傳空結果

| 檔案 | `app/routers/matches.py:91-104` |
|------|------|

**修復：**
```python
def list_matches(user=Depends(get_current_user), conn=Depends(get_db)):
    user_id = int(user["sub"])
    role = user["role"]
    repo = MatchRepository(conn)

    if role == "tutor":
        matches = repo.find_by_tutor_user_id(user_id)
    elif role == "admin":
        matches = repo.fetch_all(
            "SELECT m.*, s.subject_name, st.name AS student_name "
            "FROM ((Matches m INNER JOIN Subjects s ON m.subject_id = s.subject_id) "
            "INNER JOIN Students st ON m.student_id = st.student_id) "
            "ORDER BY m.updated_at DESC"
        )
    else:
        matches = repo.find_by_parent_user_id(user_id)
    # ...
```

---

### L18　_parse_month 允許無效月份

| 檔案 | `app/routers/stats.py:13-19` |
|------|------|

**修復：**
```python
def _parse_month(month: str | None) -> tuple[int, int]:
    if month:
        year, mon = map(int, month.split("-"))
        if not (1 <= mon <= 12):
            raise AppException("無效的月份值（1-12）")
    else:
        now = datetime.now()
        year, mon = now.year, now.month
    return year, mon
```

---

### L19　update_exam 靜默忽略 `visible_to_parent: null`

| 檔案 | `app/routers/exams.py:82-88` |
|------|------|

**修復：** 目前行為合理（null = 不更新），但可加回應提示：
```python
# 無需修改，現有行為為合理設計。若要更明確，可在 ExamUpdate model 加上 validator。
```

---

### L20　`on_event("startup")` 已棄用

| 檔案 | `app/main.py:64` |
|------|------|

**修復 — 改用 lifespan：**
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API Server 啟動")
    # startup logic here ...
    yield
    logger.info("API Server 關閉")

app = FastAPI(lifespan=lifespan, ...)
# 刪除 @app.on_event("startup") 區塊
```

---

### L21　匯出路徑為相對路徑

| 檔案 | `app/routers/admin.py:146, 229` |
|------|------|

**修復：** 同 L15，使用 config 的基礎路徑或 `Path(__file__).parent.parent / "data" / "export"`。

---

### L22　Seed / Scheduled 使用 naive datetime

| 檔案 | `seed/generator.py:66`、`app/tasks/scheduled.py:32` |
|------|------|

**修復：** 統一使用 `datetime.now(timezone.utc)` 或確保全程式碼一致使用 local time。由於 MS Access 儲存的是 local time，建議統一用 `datetime.now()`（已為現行做法），但 JWT 用 UTC 是正確的。在文件中註明此設計決策即可。

---

## 附錄：修復優先順序

```
Sprint 0（熱修復）
├── C1  SQL Injection — Repository 動態 UPDATE
├── C2  SQL Injection — CSV 匯入
├── C3  硬編碼 JWT Secret（加警告）
├── C4  硬編碼 Admin 帳密（加警告）
└── C5  SQL Wildcard Injection

Sprint 1（本週）
├── H1  Auth Store token/user 同步
├── H2  SessionForm 日期時區
├── H3  AvailabilityCalendar NaN
├── H4  Response Interceptor 防禦
├── H5  Cursor 未關閉
├── H6  CSV 匯入 rollback
├── H7  Scheduled Task Boolean
├── H8  Review 狀態檢查
└── H9  termination_reason 清洗

Sprint 2（排入迭代）
├── M1-M27（27 項 Medium）

Backlog
└── L1-L22（22 項 Low）
```
