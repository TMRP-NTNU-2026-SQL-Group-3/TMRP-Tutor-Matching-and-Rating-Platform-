# TMRP 系統 Bug 審計報告

> **審計日期**: 2026-04-08
> **審計範圍**: tutor-platform-api (Python FastAPI) + tutor-platform-web (Vue.js 3)
> **審計方法**: 靜態程式碼分析，涵蓋 API 路由、資料庫層、前端元件、前後端整合、商業邏輯五大面向

---

## 總覽

| 嚴重程度 | 數量 | 說明 |
|---------|------|------|
| **Critical** | 10 | 可能導致資料損毀、安全漏洞、系統錯誤 |
| **High** | 14 | 影響核心功能或存在潛在安全風險 |
| **Medium** | 16 | 影響使用體驗或存在效能問題 |
| **Low** | 8 | 程式碼品質或邊緣情況問題 |
| **合計** | **48** | |

---

## 一、Critical（嚴重）

### BUG-001：`@@IDENTITY` 在並發環境下的競態條件
- **檔案**: `tutor-platform-api/app/repositories/base.py:63-69`
- **分類**: 資料完整性 / 競態條件
- **說明**: `execute_returning_id()` 使用 `SELECT @@IDENTITY` 取得新插入的 ID。在 MS Access + 並發請求環境下，`@@IDENTITY` 回傳的是**整個連線層級**的最後 ID，而非當前語句的 ID。若兩個請求同時 INSERT，可能取得錯誤的 ID。
- **影響**: 新建的 match、review、session 等記錄可能被關聯到錯誤的資料。
- **建議修復**: 在同一 cursor 上下文中立即取得 ID，或實作應用層序列化。

### BUG-002：訊息發送缺乏原子性保護
- **檔案**: `tutor-platform-api/app/repositories/message_repo.py:57-70`
- **分類**: 資料完整性 / 交易處理
- **說明**: `send_message()` 依序執行 INSERT Messages → SELECT @@IDENTITY → UPDATE Conversations，三個操作之間可能被其他請求插入。若 UPDATE 失敗，訊息已寫入但 Conversation 的 `last_message_at` 未更新，造成孤立訊息。
- **建議修復**: 使用 `database_tx.transaction()` 包裹整個操作。

### BUG-003：Tutor 資料替換操作缺乏交易隔離
- **檔案**: `tutor-platform-api/app/repositories/tutor_repo.py:91-122`
- **分類**: 資料完整性 / 交易處理
- **說明**: `replace_subjects()` 和 `replace_availability()` 先 DELETE 再批次 INSERT。在 DELETE 和 INSERT 之間，其他請求可能讀到**空資料**（Dirty Read）。
- **建議修復**: 使用明確的交易上下文管理器，確保隔離性。

### BUG-004：Rate Limit 中介層可被多程序部署繞過
- **檔案**: `tutor-platform-api/app/middleware/rate_limit.py:16-55`
- **分類**: 安全性 / 速率限制
- **說明**: 速率限制使用 in-memory dict 追蹤請求次數。在多 Worker 部署下（Uvicorn 多程序），每個程序有獨立的計數器。攻擊者可繞過限制，對 `/api/auth/login` 發動暴力破解。
- **影響**: 登入端點的速率限制形同虛設。
- **建議修復**: 改用 Redis 或資料庫持久化計數；或確保僅單程序部署。

### BUG-005：Refresh Token 黑名單不持久化
- **檔案**: `tutor-platform-api/app/utils/security.py:12-13`
- **分類**: 安全性 / Token 管理
- **說明**: `_used_refresh_jti: set[str]` 存於記憶體。伺服器重啟後，所有已撤銷的 Refresh Token 重新可用。在多程序部署下，各 Worker 的黑名單獨立，攻擊者可在不同 Worker 上重複使用已輪替的 Token。此外黑名單集合無限增長，存在記憶體洩漏風險。
- **建議修復**: 將 JTI 黑名單持久化至資料庫，並加入 TTL 清理機制。

### BUG-006：Exam 更新端點缺少學生所有權驗證
- **檔案**: `tutor-platform-api/app/routers/exams.py:66-95`
- **分類**: 授權 / 存取控制
- **說明**: `update_exam()` 僅驗證 `exam["added_by_user_id"] != user_id`，但未確認該考試屬於當前家長的孩子。家長 A 若知道家長 B 孩子的 exam_id，且該考試恰好由系統或家教新增，可能繞過檢查。
- **建議修復**: 加入學生所有權驗證——確認 exam 所屬的 student 確實是當前家長的孩子。

### BUG-007：CSV Import 空值處理導致資料損毀
- **檔案**: `tutor-platform-api/app/routers/admin.py:70-76`
- **分類**: 資料完整性 / 輸入驗證
- **說明**: `_coerce_value()` 未處理空字串。CSV 中的空欄位會被當作 `""` 字串插入 BIT 欄位，造成型別不匹配錯誤或靜默資料損毀。
- **程式碼**:
  ```python
  def _coerce_value(val: str):
      if val in ('True', 'true', '1', '-1'):
          return -1
      if val in ('False', 'false', '0'):
          return 0
      return val  # ← BUG: 空字串 "" 直接回傳
  ```
- **建議修復**: 加入 `if not val or val.strip() == "": return None`。

### BUG-008：前端登出後 Store 狀態未清除
- **檔案**: `tutor-platform-web/src/stores/auth.js`（logout 函式）
- **分類**: 安全性 / 狀態管理
- **說明**: `logout()` 只清除 auth store 的資料，但 `useMatchStore`、`useMessageStore`、`useTutorStore` 中的快取資料未被重置。若使用者 A 登出後使用者 B 登入，B 可能看到 A 的配對、訊息等敏感資料。
- **建議修復**: logout 時呼叫所有相關 store 的 reset 方法。

### BUG-009：ChatView 訊息輪詢造成記憶體洩漏
- **檔案**: `tutor-platform-web/src/views/messages/ChatView.vue:120-136`
- **分類**: 元件生命週期 / 記憶體洩漏
- **說明**: `startPolling()` 在切換對話時被重複呼叫，但 `watch` 監聽路由變化時未先清除舊的 `pollTimer`。快速切換多個對話會累積多個 `setInterval`，導致記憶體洩漏和大量冗餘 API 請求。
- **建議修復**: 在 watch 回呼中先 `clearInterval(pollTimer)` 再啟動新的輪詢。

### BUG-010：Session 更新缺乏並發保護
- **檔案**: `tutor-platform-api/app/routers/sessions.py:77-128`
- **分類**: 商業邏輯 / 資料完整性
- **說明**: Session 更新的流程為：讀取舊值 → 計算差異 → 更新 + 寫入日誌。整個操作並非原子性的——兩個使用者同時更新同一 Session 時，編輯日誌可能紀錄不一致的新舊值。
- **建議修復**: 實作樂觀鎖（版本號檢查）或將整個讀取-更新流程包在交易中。

---

## 二、High（高）

### BUG-011：Match 狀態機未強制驗證前置狀態
- **檔案**: `tutor-platform-api/app/routers/matches.py:19-31, 188-191`
- **分類**: 商業邏輯 / 狀態機
- **說明**: `TRANSITIONS` 字典定義了合法的狀態轉換，但 `accept` 動作處理時未驗證目前狀態必須為 `"pending"`。若 match 已在 `"trial"` 或 `"active"` 狀態，家教仍可呼叫 accept，導致不一致的狀態。
- **建議修復**: 在處理 accept 前驗證 `current_status == "pending"`。

### BUG-012：`disagree_terminate` 從字串解析前置狀態不安全
- **檔案**: `tutor-platform-api/app/routers/matches.py:198-208`
- **分類**: 商業邏輯 / 資料完整性
- **說明**: 取消終止時，透過解析 `termination_reason` 字串重建先前狀態。若字串格式損壞，預設回復為 `'active'`，可能與實際前置狀態不符。
- **建議修復**: 在資料庫中獨立儲存 `previous_status` 欄位。

### BUG-013：Stats 查詢 NULL 值未處理
- **檔案**: `tutor-platform-api/app/repositories/stats_repo.py:12-63`
- **分類**: 資料處理 / NULL 處理
- **說明**: `income_summary()` 和 `expense_summary()` 使用 SUM/COUNT 聚合。當無匹配資料時，SUM 回傳 NULL。呼叫端對 NULL 做算術運算會出錯或產生不正確結果。
- **建議修復**: SQL 中使用 `COALESCE(SUM(...), 0)`，或在 Python 端驗證非 NULL。

### BUG-014：visible_to_parent 布林值不一致
- **檔案**: `tutor-platform-api/app/repositories/session_repo.py:56` & `exam_repo.py:61`
- **分類**: 商業邏輯 / 資料型別
- **說明**: Repository 用 `visible_to_parent = -1`（Access BIT True）做篩選，但 Router 中將回傳值當作 Python bool 處理。pyodbc 可能回傳 True/False 或 -1/0，取決於驅動設定，導致比較不一致——家長可能看不到應該可見的資料。
- **建議修復**: 統一布林處理：讀取時一律轉換為 Python bool，或查詢時用 `<> 0` 代替 `= -1`。

### BUG-015：Review Lock 排程任務存在競態條件
- **檔案**: `tutor-platform-api/app/tasks/scheduled.py:27-44`
- **分類**: 背景任務 / 並發
- **說明**: `check_expired_reviews()` 每日凌晨 3 點執行。若多個 Huey Worker 同時運行，可能同時嘗試 `ALTER TABLE ADD COLUMN`（加入 `is_locked` 欄位），導致錯誤。且無鎖定機制防止同時更新同筆 Review。
- **建議修復**: 使用 Huey 的 `@huey.lock_task()` 確保單一執行。

### BUG-016：Router 允許 Admin 存取所有角色路由
- **檔案**: `tutor-platform-web/src/router/index.js:99-102`
- **分類**: 授權 / 路由守衛
- **說明**: 路由守衛判斷 `auth.role !== requiredRole && auth.role !== 'admin'`，意味著 admin 可以存取 `/parent/*` 和 `/tutor/*` 所有路由。這可能非預期行為——admin 應有獨立儀表板。
- **建議修復**: Admin 嘗試存取非 admin 路由時應重導至 `/admin`。

### BUG-017：TutorFilter 元件 Props 變更未同步
- **檔案**: `tutor-platform-web/src/components/tutor/TutorFilter.vue:6, 51`
- **分類**: Vue 響應式 / Props
- **說明**: 元件從 `initial` prop 初始化本地 `reactive` 物件，但無 `watch` 監聽 props 變化。若父元件在掛載後更新 `initial`，篩選器 UI 不會更新。
- **建議修復**: 加入 `watch(() => props.initial, ...)` 同步本地狀態。

### BUG-018：MatchDetail 操作按鈕存在雙擊提交風險
- **檔案**: `tutor-platform-web/src/views/parent/MatchDetailView.vue:52-79` & `tutor/MatchDetailView.vue:51-82`
- **分類**: 事件處理 / 防重複提交
- **說明**: 動作按鈕用 `:disabled="actionLoading"` 防止雙擊，但 `actionLoading` 是在點擊事件**處理後**才設為 `true`。在設定前的短暫時間窗口內，使用者可能點擊兩次，送出重複的 API 請求。
- **建議修復**: 在 handler 開頭加入 `if (actionLoading.value) return` 的防禦性檢查。

### BUG-019：Review 表單提交後未重置
- **檔案**: `tutor-platform-web/src/views/parent/MatchDetailView.vue:229-244`
- **分類**: 表單狀態管理
- **說明**: `reviewForm` 以硬編碼初始值建立。提交成功後未重置表單。若使用者對不同 match 撰寫評價，會看到上次的表單內容。
- **建議修復**: 在 `submitReview()` 成功後重置表單欄位。

### BUG-020：Admin 匯出檔名未驗證路徑遍歷
- **檔案**: `tutor-platform-api/app/routers/admin.py:149-172`
- **分類**: 安全性 / 路徑遍歷
- **說明**: `export_csv()` 接收 `table_name` 作為路徑參數。雖有 `ALLOWED_TABLES` 白名單驗證，但回應的檔名組裝邏輯若白名單驗證被移除或繞過，可能遭受路徑遍歷攻擊。
- **建議修復**: 對產出的檔名做額外的清理（sanitize），確保不包含路徑分隔符。

### BUG-021：SQL 動態建構風險（Admin 路由）
- **檔案**: `tutor-platform-api/app/routers/admin.py:128, 158, 195-201`
- **分類**: 安全性 / SQL 注入
- **說明**: 雖有 ALLOWED_TABLES 白名單，但 table name 和 column name 仍以 f-string 直接嵌入 SQL。若白名單設定錯誤或未來修改不當，可能造成 SQL 注入。
- **建議修復**: 使用映射字典代替字串插值，避免直接在 f-string 中使用使用者輸入。

### BUG-022：Admin Import-All 未驗證外鍵約束
- **檔案**: `tutor-platform-api/app/routers/admin.py:356-387`
- **分類**: 資料完整性 / 匯入
- **說明**: 批次匯入使用單一交易，但未預先驗證外鍵參照。若 CSV 中包含不存在的 tutor_id，INSERT 失敗會導致整筆交易 rollback，先前匯入的有效資料表也全部遺失，且無詳細錯誤訊息。
- **建議修復**: 匯入前預先驗證外鍵，或提供每筆資料的錯誤詳情。

### BUG-023：Session 更新 SQL 動態建構風險
- **檔案**: `tutor-platform-api/app/routers/sessions.py:115-118`
- **分類**: 安全性 / SQL 注入
- **說明**: 使用 f-string 建構 UPDATE 的 SET 子句：`f"UPDATE Sessions SET {set_clause}..."`。雖有 `validate_columns()` 白名單驗證，但此模式若白名單被修改，風險極高。
- **建議修復**: 使用參數化查詢建構器，而非字串格式化。

### BUG-024：Exam 建立缺乏角色限制
- **檔案**: `tutor-platform-api/app/routers/exams.py:12-40`
- **分類**: 授權 / 存取控制
- **說明**: `create_exam()` 使用 `get_current_user` 但未限制角色。判斷邏輯依賴 `is_parent` / `is_tutor` 檢查，但 admin 角色嘗試建立考試會失敗。更關鍵的是，家長建立考試時只檢查「是否為家長」，未驗證該學生是否為自己的孩子。
- **建議修復**: 加入 `require_role("parent", "tutor")` 或嚴格驗證學生所有權。

---

## 三、Medium（中等）

### BUG-025：分頁實作載入全部資料至記憶體
- **檔案**: `tutor-platform-api/app/repositories/base.py:71-84`
- **分類**: 效能
- **說明**: `fetch_paginated()` 先載入所有結果到記憶體，再用 Python 切片取得分頁。這是 MS Access 不支援 LIMIT/OFFSET 的 workaround，但對大資料表（數千筆以上）會造成嚴重的記憶體和效能問題。
- **建議修復**: 記錄此限制並考慮快取機制，或使用 cursor-based pagination。

### BUG-026：資料庫重試邏輯使用固定延遲
- **檔案**: `tutor-platform-api/app/database.py:24-33`
- **分類**: 可靠性 / 資料庫連線
- **說明**: `get_connection()` 重試 3 次，每次固定 0.5 秒延遲。對 MS Access 檔案鎖定場景，此延遲太短。
- **建議修復**: 改用指數退避（exponential backoff）+ jitter。

### BUG-027：交易上下文管理器不支援巢狀交易
- **檔案**: `tutor-platform-api/app/database_tx.py:4-24`
- **分類**: 資料庫模式
- **說明**: `transaction()` 設定 `autocommit = False` 並手動 commit。若巢狀使用（一個交易呼叫另一個 repository 方法），內層的 commit 會提前提交外層的變更，破壞交易隔離性。
- **建議修復**: 實作 savepoint 機制或明確文件化禁止巢狀使用。

### BUG-028：CORS Origin 解析未去除空白
- **檔案**: `tutor-platform-api/app/main.py:80-86`
- **分類**: 設定 / CORS
- **說明**: `settings.cors_origins.split(",")` 未對各項做 `.strip()`。若環境變數中包含空格（如 `"http://localhost:5173, http://localhost:3000"`），第二個 origin 會因前導空格而匹配失敗。
- **建議修復**: 使用 `[o.strip() for o in settings.cors_origins.split(",")]`。

### BUG-029：useMatchDetail 存在請求競態條件
- **檔案**: `tutor-platform-web/src/composables/useMatchDetail.js:36-57`
- **分類**: 非同步 / 競態條件
- **說明**: `fetchMatch()` 發送 3 個平行 API 請求。若使用者快速切換不同 match，舊請求的回應可能在新請求之後到達，覆蓋正確的資料。
- **建議修復**: 加入 requestId 追蹤或使用 AbortController 取消過時的請求。

### BUG-030：StudentsView 表單錯誤狀態未清除
- **檔案**: `tutor-platform-web/src/views/parent/StudentsView.vue:104-119`
- **分類**: 表單狀態管理
- **說明**: 新增學生成功後表單關閉，但若再次開啟，之前的錯誤訊息仍可能殘留。
- **建議修復**: 在表單顯示時清除 `error.value`。

### BUG-031：ProfileView 未取消未完成的非同步請求
- **檔案**: `tutor-platform-web/src/views/tutor/ProfileView.vue:142-195`
- **分類**: 元件生命週期
- **說明**: `onMounted` 中發送 API 請求，但導航離開時不會取消。若使用者在載入中離開頁面，Promise 解決時嘗試更新已卸載的元件狀態。
- **建議修復**: 使用 AbortController 或 flag 標記元件是否仍掛載。

### BUG-032：InviteForm 可見性變化時表單未重置
- **檔案**: `tutor-platform-web/src/components/match/InviteForm.vue:95-102`
- **分類**: 表單狀態管理
- **說明**: `reset()` 由父元件呼叫。若 Modal 被銷毀重建，表單可能引用過期資料。
- **建議修復**: 加入 `watch(() => props.visible, (v) => { if (v) reset() })`。

### BUG-033：TutorDetailView 錯誤狀態未在表單重開時清除
- **檔案**: `tutor-platform-web/src/views/parent/TutorDetailView.vue:144-164`
- **分類**: 表單驗證 / 錯誤處理
- **說明**: `submitInvite()` 設定 `inviteError`，但關閉表單後重開，舊的錯誤訊息仍然顯示。
- **建議修復**: 監聽 `showInviteForm` 變化，開啟時清除錯誤。

### BUG-034：ConversationListView 無自動刷新
- **檔案**: `tutor-platform-web/src/views/messages/ConversationListView.vue:47-56`
- **分類**: 狀態管理 / 資料新鮮度
- **說明**: 對話列表只在掛載時載入一次，不會自動刷新。新訊息到達時列表不會更新，除非使用者手動導航離開再回來。
- **建議修復**: 加入定時輪詢或 WebSocket 即時更新。

### BUG-035：缺少關鍵 Join 操作的索引
- **檔案**: `tutor-platform-api/app/init_db.py:289-301`
- **分類**: 效能 / 索引
- **說明**: 缺少以下索引：`Tutor_Subjects.subject_id`、`Sessions.created_at`、`Matches(status, updated_at)` 複合索引。影響家教搜尋和配對查詢效能。
- **建議修復**: 在 init_db.py 中加入對應索引。

### BUG-036：Admin 操作缺乏審計日誌
- **檔案**: `tutor-platform-api/app/routers/admin.py`
- **分類**: 稽核 / 安全性
- **說明**: 資料庫重置、匯入、匯出等破壞性管理員操作未記錄執行者和時間。若管理員帳號被盜，無法追蹤操作紀錄。
- **建議修復**: 為所有管理員操作加入帶有使用者 ID 和時間戳的 WARNING 級別日誌。

### BUG-037：Rate Limit 中介層過期 Bucket 未主動清理
- **檔案**: `tutor-platform-api/app/middleware/rate_limit.py:36-42`
- **分類**: 效能 / 記憶體洩漏
- **說明**: 過期的速率限制記錄僅在同路徑 IP 數超過 10,000 時才清理。流量停止後舊記錄永遠留在記憶體中。
- **建議修復**: 加入定時清理機制或 TTL 淘汰策略。

### BUG-038：Admin 密碼預設值只警告不阻擋
- **檔案**: `tutor-platform-api/app/config.py:33-44`
- **分類**: 安全性 / 設定
- **說明**: JWT_SECRET_KEY 使用預設值時會報錯阻擋啟動（正確），但 ADMIN_PASSWORD 使用預設值時僅發出警告，不阻擋。行為不一致。
- **建議修復**: 統一處理——兩者都應阻擋啟動，或至少在 production 環境下阻擋。

### BUG-039：缺少 Logout API 端點
- **檔案**: `tutor-platform-api/app/routers/auth.py`
- **分類**: Token 管理
- **說明**: 無登出 API。使用者無法主動撤銷 Token，只能等待 Token 過期。
- **建議修復**: 實作 `/api/auth/logout` 端點，將 access token 和 refresh token 加入黑名單。

### BUG-040：Health Check 端點洩漏資料庫狀態
- **檔案**: `tutor-platform-api/app/routers/health.py:12-24`
- **分類**: 資訊洩漏
- **說明**: `/health` 端點無需認證即可存取，且回傳資料庫連線狀態。攻擊者可利用此端點進行偵察。
- **建議修復**: 對未認證請求只回傳簡要狀態（如 `{"status": "ok"}`），隱藏資料庫細節。

---

## 四、Low（低）

### BUG-041：base.py close() 靜默吞掉例外
- **檔案**: `tutor-platform-api/app/repositories/base.py:18`
- **分類**: 錯誤處理
- **說明**: `close()` 中的 `except Exception: pass` 完全忽略錯誤，使連線池問題難以除錯。
- **建議修復**: 改為 `logger.exception("Failed to close cursor")` 後再 pass。

### BUG-042：day_of_week 缺乏資料庫層級約束
- **檔案**: `tutor-platform-api/app/models/tutor.py:27-45` & `init_db.py:110`
- **分類**: 資料驗證
- **說明**: Pydantic 模型驗證 0-6，但資料庫 Schema 為 SHORT 無約束。直接操作 DB 可寫入無效值。
- **建議修復**: 加入 CHECK 約束 `CHECK (day_of_week >= 0 AND day_of_week <= 6)`。

### BUG-043：Seed Generator 使用錯誤的 Access 日期基準
- **檔案**: `tutor-platform-api/seed/generator.py:242-245`
- **分類**: 資料處理 / 日期時間
- **說明**: 使用 `datetime(1899, 12, 30)` 作為 Access 日期基準，且無時區處理。所有時間皆為 naive datetime。
- **建議修復**: 統一使用 UTC 並在顯示層轉換時區。

### BUG-044：SessionForm 小時數缺少上限驗證
- **檔案**: `tutor-platform-web/src/components/session/SessionForm.vue:18-20`
- **分類**: 表單驗證
- **說明**: hours 輸入有 `min="0.5" step="0.5"` 但無 max 限制，使用者可填入不合理的數值（如 999 小時）。
- **建議修復**: 加入 `max="24"` 或類似合理上限。

### BUG-045：RadarChart 無錯誤邊界
- **檔案**: `tutor-platform-web/src/components/review/RadarChart.vue:14-71`
- **分類**: 錯誤處理
- **說明**: 若 Chart.js 渲染失敗或資料格式無效，無 fallback UI 或 try-catch。
- **建議修復**: 加入 try-catch 和 fallback 顯示。

### BUG-046：AdminDashboardView 初始載入無 Loading 狀態
- **檔案**: `tutor-platform-web/src/views/admin/AdminDashboardView.vue:155-165`
- **分類**: 使用者體驗
- **說明**: 使用者列表在 onMounted 載入，但初始載入期間無 skeleton 或 loading 指示器。
- **建議修復**: 加入初始載入的 loading 狀態。

### BUG-047：Logger 環境變數存取不一致
- **檔案**: `tutor-platform-api/app/utils/logger.py:40`
- **分類**: 設定 / 一致性
- **說明**: 直接使用 `os.environ.get("LOG_FORMAT")` 而非 Settings 物件，可能造成大小寫不一致問題。
- **建議修復**: 統一從 Settings 物件讀取設定值。

### BUG-048：測試 Mock 設定不夠穩健
- **檔案**: `tutor-platform-api/tests/conftest.py:28-34`
- **分類**: 測試 / Mock 設定
- **說明**: `get_db` mock 使用簡單的 `lambda: mock_conn`，若測試中修改 mock 行為，後續呼叫可能出錯。
- **建議修復**: 使用 `side_effect` 處理多次呼叫，並確保每個測試前重置 mock。

---

## 五、修復優先順序建議

### 第一優先（立即修復）- 安全與資料完整性
1. **BUG-005** - Refresh Token 黑名單持久化（安全性）
2. **BUG-004** - Rate Limit 多程序繞過（安全性）
3. **BUG-008** - 前端登出未清除 Store（隱私）
4. **BUG-001** - @@IDENTITY 競態條件（資料完整性）
5. **BUG-006** - Exam 所有權驗證（授權）
6. **BUG-007** - CSV Import 空值處理（資料損毀）

### 第二優先（短期修復）- 核心功能
7. **BUG-002** - 訊息發送原子性
8. **BUG-003** - Tutor 資料替換交易
9. **BUG-009** - ChatView 記憶體洩漏
10. **BUG-010** - Session 更新並發
11. **BUG-011** - Match 狀態機驗證
12. **BUG-013** - Stats NULL 處理
13. **BUG-039** - 新增 Logout 端點

### 第三優先（中期改善）- 體驗與效能
14. **BUG-014** - 布林值一致性
15. **BUG-018** - 防雙擊提交
16. **BUG-025** - 分頁效能
17. **BUG-028** - CORS 空白處理
18. **BUG-029** - useMatchDetail 競態
19. **BUG-035** - 資料庫索引

### 第四優先（長期維護）- 其餘項目
20. 其餘 Medium 和 Low 等級的 Bug

---

## 六、架構性建議

| 面向 | 現況 | 建議 |
|------|------|------|
| **Token 管理** | 記憶體黑名單，無 Logout | 改用 Redis/DB 持久化黑名單，新增 Logout API |
| **資料庫並發** | MS Access 單檔鎖定 | 考慮遷移至 SQLite/PostgreSQL 以獲得更好的並發支援 |
| **交易管理** | 部分使用 transaction() | 統一所有多步驟操作使用交易上下文管理器 |
| **速率限制** | 記憶體計數器 | 改用 Redis 計數器以支援多程序 |
| **前端狀態** | 各 Store 獨立管理 | 實作全域 reset 方法，在 logout 時統一清除 |
| **錯誤處理** | 部分端點缺乏 | 統一使用 AppException 體系 |
| **Schema 遷移** | 散落在程式碼中 | 建立集中式遷移機制 |

---

*本報告由靜態程式碼分析產出，未涵蓋實際執行時的動態測試。建議搭配整合測試進一步驗證。*
