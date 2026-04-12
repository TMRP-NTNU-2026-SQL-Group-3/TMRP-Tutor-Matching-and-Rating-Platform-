# TMRP 系統性 Bug 審計報告

> **審計日期**：2026-04-12
> **審計範圍**：後端 API（FastAPI + PostgreSQL）、前端（Vue 3 + Vite）、基礎設施（Docker + Nginx）
> **審計方法**：全面靜態程式碼分析

---

## 摘要

| 嚴重等級 | 數量 |
|---------|------|
| CRITICAL | 2 |
| HIGH | 8 |
| MEDIUM | 12 |
| LOW | 6 |
| **總計** | **28** |

---

## 一、基礎設施與部署（Docker / Nginx）

### [CRITICAL] 1. Docker Compose 缺少 API 健康檢查定義

- **檔案**：`docker-compose.yml` 第 20-31 行
- **問題**：`web` 服務設定了 `condition: service_healthy` 依賴 `api`，但 `api` 服務在 docker-compose 中沒有定義 `healthcheck`。雖然 Dockerfile 中定義了 healthcheck，但 docker-compose 無法讀取 Dockerfile 內的 healthcheck 設定來判斷服務是否就緒。
- **影響**：`web` 容器會無限等待或超時，導致整個系統無法啟動。
- **修復**：在 docker-compose.yml 的 `api` 服務中加入 healthcheck 區段。

### [HIGH] 2. Nginx 反向代理路徑未正確剝離 `/api/` 前綴

- **檔案**：`tutor-platform-web/nginx.conf` 第 9-10 行
- **問題**：
  ```nginx
  location /api/ {
      proxy_pass http://api:8000;
  }
  ```
  當請求 `/api/auth/login` 時，nginx 會將完整路徑 `/api/auth/login` 轉發給後端，但後端路由期望的是 `/auth/login`。
- **影響**：在 Docker 生產環境中，所有 API 請求都會得到 404 回應。
- **修復**：改為 `proxy_pass http://api:8000/;`（加上尾部斜線以剝離前綴）。

### [HIGH] 3. 前端 `VITE_API_BASE_URL` 空字串導致請求失敗

- **檔案**：`tutor-platform-web/Dockerfile` 第 12-15 行、`docker-compose.yml` 第 49 行
- **問題**：Docker 建置時傳入 `VITE_API_BASE_URL: ""`（空字串）。前端程式碼使用 `??`（nullish coalescing）做降級：
  ```javascript
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
  ```
  空字串不是 `null` 或 `undefined`，所以 `??` 不會觸發降級，baseURL 變成 `""`。
- **影響**：Docker 環境中 API 請求路徑不正確，前端功能全面失效。
- **修復**：docker-compose.yml 改為 `VITE_API_BASE_URL: "/api"`，或前端改用 `||` 運算子。

### [HIGH] 4. CORS 來源設定不一致

- **檔案**：
  - `tutor-platform-api/.env` 第 10 行：`CORS_ORIGINS=http://localhost:5273`
  - `tutor-platform-api/.env.docker` 第 18 行：`CORS_ORIGINS=http://localhost,http://localhost:80`
- **問題**：開發環境 CORS 允許 5273 埠，但 vite.config.js 設定的 dev server 埠也是 5273，看似匹配；然而 `.env.example` 中寫的是 5173，可能造成其他開發者設定錯誤。Docker 環境中的 CORS 設定需確保與 nginx 的請求來源完全吻合。
- **影響**：跨域請求被瀏覽器攔截，前端無法與 API 通訊。

### [LOW] 5. 開發環境埠號不一致

- **檔案**：`tutor-platform-web/vite.config.js` 第 14 行
- **問題**：dev server 使用 5273 埠，但 `.env.example` 中 CORS 設定為 5173。
- **影響**：新開發者若依照 `.env.example` 設定，本地開發時會遇到 CORS 錯誤。

---

## 二、後端 API

### 資料庫與交易管理

### [HIGH] 6. 連線池未初始化保護

- **檔案**：`app/shared/infrastructure/database.py` 第 28-43 行
- **問題**：`get_db()` 依賴注入直接呼叫 `_pool.getconn()`，但若 `_pool` 尚未初始化（為 `None`），會拋出 `AttributeError`。
- **影響**：在特定部署場景下（如測試、非標準啟動流程），伺服器會崩潰。
- **修復**：加入 `if _pool is None: raise RuntimeError("Database pool not initialized")` 防禦性檢查。

### [HIGH] 7. 直接使用 cursor.execute() 繞過 Repository 層

- **檔案**：
  - `app/routers/sessions.py` 第 124-135 行
  - `app/teaching/api/session_router.py` 第 87-95 行
- **問題**：在 `transaction()` 上下文中直接使用 `repo.cursor.execute()` 而非透過 Repository 的 `execute()` 方法：
  ```python
  repo.cursor.execute(
      f"UPDATE sessions SET {set_clause}, updated_at = NOW() WHERE session_id = %s",
      list(updates.values()) + [session_id],
  )
  ```
- **影響**：繞過了 Repository 層的錯誤處理和日誌紀錄，且在多行程部署下可能產生競態條件。交易回滾行為不一致。

### [MEDIUM] 8. SQL 字串插值的維護風險

- **檔案**：`app/catalog/infrastructure/postgres_tutor_repo.py` 第 105、112 行
- **問題**：使用 f-string 組建 SQL 的 SET 子句。雖然有 `validate_columns()` 白名單驗證，但依賴正規表達式 `[A-Za-z_][A-Za-z0-9_]*`，未來維護者可能繞過驗證。
- **影響**：目前安全，但屬於脆弱設計，長期有 SQL 注入風險。

### [MEDIUM] 9. 交易巢狀邏輯脆弱

- **檔案**：`app/shared/infrastructure/database_tx.py` 第 20-23 行
- **問題**：當偵測到已在交易中時，直接 `yield conn` 並 `return`。邏輯正確但脆弱——若未來有人移除 `return`，會導致雙重 commit/rollback。
- **影響**：目前安全，但缺乏防禦性設計。

### 安全性

### [HIGH] 10. 通用例外處理器遮蔽錯誤細節

- **檔案**：`app/main.py` 第 65-70 行
- **問題**：
  ```python
  async def unhandled_exception_handler(request, exc: Exception):
      logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
      return JSONResponse(status_code=500, content={...})
  ```
  雖然有日誌記錄，但在生產環境中缺乏結構化錯誤追蹤（如 Sentry），管理員難以定位問題。
- **影響**：生產環境除錯困難，錯誤被靜默吞噬。

### [MEDIUM] 11. In-Memory Refresh Token 黑名單在多 Worker 下失效

- **檔案**：`app/shared/infrastructure/security.py` 第 13-19 行
- **問題**：使用 Python dict 儲存已使用的 refresh token JTI：
  ```python
  _used_refresh_jti: dict[str, float] = {}
  ```
  程式碼中有註解說明此限制，但未有任何防護措施。
- **影響**：在 `uvicorn --workers 4` 部署下，Worker 1 登出的 token 在 Worker 2-4 仍可使用，存在 token 重放攻擊風險。

### [MEDIUM] 12. In-Memory 速率限制在多 Worker 下失效

- **檔案**：`app/middleware/rate_limit.py` 第 22-28 行
- **問題**：與上述相同，速率計數器為各 Worker 獨立維護。
- **影響**：攻擊者可透過多個 Worker 繞過速率限制，存在 DoS 風險。

### [MEDIUM] 13. .env 檔案包含硬編碼管理員密碼

- **檔案**：`tutor-platform-api/.env` 第 6 行
- **問題**：`ADMIN_PASSWORD=<實際密碼>` 直接寫在可能被版本控制追蹤的檔案中。
- **影響**：若 `.env` 被提交至 Git，密碼將外洩。即使在 `.gitignore` 中，仍屬不良實踐。

### [MEDIUM] 14. 過度寬泛的例外捕獲（Bare `except Exception`）

- **檔案**：多個檔案，如 `app/admin/api/router.py` 第 131 行、`app/routers/admin.py` 第 157 行
- **問題**：
  ```python
  except Exception:
      pass  # 靜默吞噬所有錯誤
  ```
- **影響**：合法的錯誤被無聲忽略，除錯時無法追蹤問題根源。

### 架構問題

### [MEDIUM] 15. 新舊路由模組並存（死碼）

- **檔案**：
  - 舊路由：`app/routers/`（13 個路由檔案）
  - 新 DDD 路由：`app/*/api/router.py`
- **問題**：`main.py` 僅載入新 DDD 路由，舊 `app/routers/` 目錄下的檔案成為死碼。
- **影響**：維護混亂，新開發者可能誤修改舊路由而不生效。
- **修復**：刪除 `app/routers/` 目錄或標記為已棄用。

### [LOW] 16. 雙重例外類別體系

- **檔案**：
  - 舊：`app/exceptions.py`（`ConflictException`, `AppException`, `NotFoundException`, `ForbiddenException`）
  - 新：`app/shared/domain/exceptions.py`（`ConflictError`, `DomainException`, `NotFoundError`, `PermissionDeniedError`）
- **問題**：兩套平行的例外類別，`main.py` 中有兩組例外處理器註冊。
- **影響**：程式碼重複、命名混亂，長期維護成本高。

### [LOW] 17. 資料庫初始化時序風險

- **檔案**：`app/main.py` 第 82-91 行
- **問題**：資料庫初始化在 lifespan startup hook 中執行，但 Docker healthcheck 可能在初始化完成前就開始查詢資料庫。
- **影響**：啟動初期短暫的健康檢查失敗，可能觸發容器重啟。

---

## 三、前端 Web

### 認證與 API 層

### [HIGH] 18. Token 刷新競態條件

- **檔案**：`tutor-platform-web/src/api/index.js` 第 10-15、48-57、74-75 行
- **問題**：`pendingRequests` 佇列和 `isRefreshing` 旗標為模組級全域狀態。當多個請求同時收到 401 錯誤時，佇列處理非原子性操作，可能導致請求以錯誤的 token 重送或順序錯亂。
- **影響**：並發場景下可能出現認證失敗、token 洩漏或無限重試迴圈。

### [MEDIUM] 19. 登出功能 baseURL 硬編碼

- **檔案**：`tutor-platform-web/src/stores/auth.js` 第 52 行
- **問題**：登出流程獨立計算 baseURL：
  ```javascript
  const baseURL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
  ```
  而非使用已配置的 axios 實例。
- **影響**：在 Docker 生產環境中，登出請求會發送到 `localhost:8000`（不存在），導致登出失敗但前端仍清除本地狀態，造成不一致。

### 元件與檢視

### [MEDIUM] 20. SearchView 零值篩選失效

- **檔案**：`tutor-platform-web/src/views/parent/SearchView.vue` 第 45-46 行
- **問題**：使用 falsy 檢查而非 null 檢查：
  ```javascript
  if (filters.min_rate) { ... }  // 0 會被視為 false
  if (filters.max_rate) { ... }
  ```
- **影響**：若使用者設定最低費率為 0，篩選條件不會被套用。雖然實際場景中 0 費率不常見，但屬於語意錯誤。

### [MEDIUM] 21. ChatView 訊息輪詢效能問題

- **檔案**：`tutor-platform-web/src/views/messages/ChatView.vue` 第 120-123 行
- **問題**：每 5 秒輪詢一次，每次都取回全部訊息歷史，沒有分頁或增量更新機制。若路由快速切換，舊路由的計時器可能仍在執行。
- **影響**：訊息量大時效能顯著下降；可能的記憶體洩漏。

### [MEDIUM] 22. ConversationListView 錯誤狀態未清除

- **檔案**：`tutor-platform-web/src/views/messages/ConversationListView.vue` 第 49-54 行
- **問題**：`fetchConversations()` 可以設定 `error.value`，但在重新取得資料前沒有清除舊的錯誤訊息。
- **影響**：即使重新載入成功，使用者仍可能看到過時的錯誤訊息。

### [MEDIUM] 23. ProfileView 載入狀態在元件卸載後不一致

- **檔案**：`tutor-platform-web/src/views/tutor/ProfileView.vue` 第 199 行
- **問題**：`finally` 區塊中的 `loading.value = false` 受 `isMounted` 保護，但若元件在非同步操作期間卸載，載入狀態永遠不會重置。
- **影響**：下次進入頁面時可能看到持續的載入骨架畫面。

### [MEDIUM] 24. ExamForm 提交前缺少資料驗證

- **檔案**：`tutor-platform-web/src/views/tutor/MatchDetailView.vue` 第 418 行
- **問題**：`submitExam()` 使用 `match.value.student_id` 和 `match.value.subject_id`，但未檢查 `match.value` 是否存在或欄位是否已填充。
- **影響**：若配對資料載入失敗，會發送包含 null/undefined ID 的 API 請求。

### [LOW] 25. ConversationListView 點擊區域無回饋

- **檔案**：`tutor-platform-web/src/views/messages/ConversationListView.vue` 第 12 行
- **問題**：當 `conversation_id` 為 null 時，點擊事件不會觸發導航，但 UI 上沒有視覺回饋表示該項目不可點擊。
- **影響**：使用者體驗不佳——點擊後無任何反應。

### [LOW] 26. useMatchDetail 缺少路由參數驗證

- **檔案**：`tutor-platform-web/src/composables/useMatchDetail.js` 第 45 行
- **問題**：直接使用 `route.params.id` 呼叫 API，未驗證其是否為有效值。
- **影響**：直接訪問 `/parent/match/` 或 `/parent/match/abc` 時，錯誤訊息不夠明確。

### [LOW] 27. FormData 上傳缺少明確的 Content-Type 處理

- **檔案**：`tutor-platform-web/src/api/admin.js` 第 26 行
- **問題**：`importAll` 直接將 FormData 傳入 `api.post()`，依賴 axios 自動設定 `Content-Type`。若 axios 攔截器覆蓋了 headers，FormData 可能被錯誤序列化。
- **影響**：在特定配置下匯入功能可能失敗。

### [LOW] 28. 家長版評論表單重置遺漏 review_type

- **檔案**：`tutor-platform-web/src/views/parent/MatchDetailView.vue` 第 254-258 行
- **問題**：提交評論後重置表單時未包含 `review_type`，而教師版（tutor/MatchDetailView.vue 第 375-381 行）有正確處理。
- **影響**：功能上無大礙（家長固定為 `parent_to_tutor`），但屬於不一致的實作。

---

## 四、最高優先級修復建議

### 必須立即修復（部署阻斷）

| 優先級 | Bug # | 問題 | 影響範圍 |
|--------|-------|------|---------|
| P0 | #1 | Docker Compose 缺少 healthcheck | 系統無法啟動 |
| P0 | #2 | Nginx 未剝離 `/api/` 前綴 | 生產環境 API 全部 404 |
| P0 | #3 | VITE_API_BASE_URL 空字串問題 | 前端無法連接 API |

### 應盡快修復（功能性問題）

| 優先級 | Bug # | 問題 | 影響範圍 |
|--------|-------|------|---------|
| P1 | #4 | CORS 設定不一致 | 跨域請求失敗 |
| P1 | #6 | 連線池未初始化保護 | 特定情境下崩潰 |
| P1 | #7 | 直接使用 cursor.execute() | 交易一致性風險 |
| P1 | #10 | 通用例外處理器 | 生產除錯困難 |
| P1 | #18 | Token 刷新競態條件 | 並發認證失敗 |
| P1 | #19 | 登出 baseURL 錯誤 | 生產環境登出失敗 |

### 中期改善（安全性與效能）

| 優先級 | Bug # | 問題 | 影響範圍 |
|--------|-------|------|---------|
| P2 | #11 | In-Memory Token 黑名單 | 多 Worker 安全風險 |
| P2 | #12 | In-Memory 速率限制 | 多 Worker DoS 風險 |
| P2 | #13 | 硬編碼管理員密碼 | 密碼外洩風險 |
| P2 | #21 | 訊息輪詢效能 | 大量訊息時卡頓 |

### 長期重構

| 優先級 | Bug # | 問題 | 影響範圍 |
|--------|-------|------|---------|
| P3 | #15 | 新舊路由並存 | 維護混亂 |
| P3 | #16 | 雙重例外體系 | 程式碼重複 |

---

*本報告由靜態分析產生，建議搭配實際部署測試驗證各項問題。*
