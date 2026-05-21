<p align="center">
  <img src="../TMRP-LOGO.png" alt="TMRP — Tutor Matching and Rating Platform" width="320" />
</p>

# TMRP — Demo 腳本與彩排手冊

**用途:** 課堂口頭報告 + 系統演示的執行腳本。涵蓋兩種交付形式 ——
**Part A:實體現場 demo(約 20 分鐘)** 與 **Part B:YouTube 介紹影片(時間不限)**。
**核心策略:** 這是一門 SQL 課,**資料庫設計是主角**;先秀產品讓觀眾確認系統是真的,再「掀開引擎蓋」用 `psql` 展示 schema、約束、trigger、materialized view。

---

## 目錄

**共用基礎**
1. [已驗證的 schema 事實](#1-已驗證的-schema-事實)
2. [環境前置與檢查清單](#2-環境前置與檢查清單)
3. [帳號策略](#3-帳號策略)
4. [資料庫深掘 SQL 腳本](#4-資料庫深掘-sql-腳本)
5. [Q&A 預備](#5-qa-預備)

**Part A — 實體現場 demo（約 20 分鐘）**
6. [時間總表與分工](#6-part-a--時間總表與分工)
7. [逐段腳本](#7-part-a--逐段腳本)
8. [風險預案](#8-part-a--風險預案)

**Part B — YouTube 介紹影片**
9. [影片規格與章節總表](#9-part-b--影片規格與章節總表)
10. [逐章腳本](#10-part-b--逐章腳本)
11. [錄製與後製建議](#11-part-b--錄製與後製建議)

---

## 1. 已驗證的 schema 事實

> 以下已對照 `app/init_db.py`、`app/main.py`、`seed/generator.py` 原始碼確認(2026-05-21)。
> 本節內容已與 `docs/database-schema.md`、`docs/architecture.md` 同步更新一致(2026-05-21)。D、E 兩位請熟記。

| 項目 | 實際情況 |
|---|---|
| Trigger 數量 | **3 個**(非文件所稱的 5 個):`trg_matches_set_parent`、`trg_students_propagate_parent`、`trg_conversations_order_pair` |
| Materialized view 刷新 | **不是 trigger 刷新。** M-09 變更已刪除刷新 trigger;改由 `main.py` 的背景任務 `_run_periodic_mv_refresh()` **每 30 秒**執行 `REFRESH MATERIALIZED VIEW CONCURRENTLY` |
| Materialized view | `v_tutor_ratings`(評分聚合)、`v_tutor_active_students`(在學學生數);各有 `tutor_id` 唯一索引,故可用 `CONCURRENTLY` 刷新 |
| Composite PK | `tutor_subjects (tutor_id, subject_id)`、`idempotency_keys (user_id, idem_key)` |
| Partial unique index | `idx_matches_one_active` ON `matches (tutor_id, student_id, subject_id) WHERE status IN ('pending','trial','active','paused','terminating')` |
| CHECK 約束 | `chk_users_role`、`chk_subject_category`、評分 1–5、`day_of_week 1–7`、`start_time < end_time`、match status enum、`user_a_id < user_b_id` |

彩排時用這兩條 SQL 自我核對(以資料庫現況為準,不要相信舊文件):

```sql
SELECT tgname, tgrelid::regclass AS table_name
FROM pg_trigger WHERE NOT tgisinternal ORDER BY 2;   -- 應列出 3 個 trigger

\dm                                                   -- 應列出 2 個 materialized view
```

---

## 2. 環境前置與檢查清單

### 啟動(demo / 錄影前一天完成)

- [ ] 把未提交的 docker 設定**定版並 commit**;最後一次彩排後不再改任何設定。
- [ ] `docker compose up -d --build` 啟動。會自動載入 `docker-compose.override.yml`,把 DB 綁 `127.0.0.1:41432`、API 綁 `127.0.0.1:41000`(供 `psql` 與健康檢查連線)。
- [ ] 在 `tutor-platform-api/.env.docker` 設 **`DEBUG=false`**(讓 `/seed` 能正常灌資料);此模式下啟動驗證器要求 **`COOKIE_SECURE=true`**,一併設好,否則 API 拒絕啟動。瀏覽器把 `localhost` 視為安全來源,Secure cookie 在 `http://localhost` 仍可正常登入。本 demo 不使用 Swagger `/docs`。
- [ ] `docker compose ps` 確認 **4 個容器(db / api / worker / web)全部 healthy** —— worker 沒跑,收入/支出統計會一直轉圈。

### 灌種子資料(順序很重要)

- [ ] **先**用 admin 登入 → 後台 → 「生成假資料」(或 `POST /api/admin/seed`)。
- [ ] **種子有冪等守衛:只要已存在非 admin 使用者就會整個跳過。** 所以順序是「先 seed,再註冊自己的 demo 帳號」。(注意:若 `DEBUG=true`,開機會自動建立 `tutor`/`parent` demo 帳號,`/seed` 會被跳過 —— 這正是本 demo 採 `DEBUG=false` 的原因。)
- [ ] 取得種子帳號密碼(隨機 16 字,只印在 log):
  ```powershell
  docker compose logs api | Select-String "SEED CREDENTIALS" -Context 0,7
  ```
  把 `tutor_zhang`(張家豪)的密碼抄到小抄上 —— 現場會用它登入家教端。

### 開場前

- [ ] 兩個瀏覽器設定檔(或一般 + 無痕)並排:家長一邊、家教一邊。媒合的 `terminate → agree_terminate` 需要對方確認,反覆登入登出會拖垮節奏。
- [ ] 把 [§4](#4-資料庫深掘-sql-腳本) 的 SQL 存成 `demo.sql`,現場用 `psql ... -f demo.sql` 或逐段貼,**不要手打**。
- [ ] 預開分頁:前端、psql 終端、`tutor-platform-api/data/tutoring.accdb`、簡報。
- [ ] 瀏覽器與終端字級放大;`psql` 執行 `\x auto` 讓寬結果自動轉直式。
- [ ] 用 §1 的兩條核對 SQL 確認 trigger / MV 與腳本一致。
- [ ] **錄一支備案影片**(現場版專用):docker / 投影出狀況時直接播。

---

## 3. 帳號策略

| 角色 | 來源 | 用途 |
|---|---|---|
| admin | 系統首次啟動自動建立(帳號見 `.env.docker` 的 `ADMIN_USERNAME`、密碼見 `secrets/admin_password.txt`) | 後台、灌種子 |
| 家長 | **現場 / 鏡頭前新註冊** | demo 的「真實感」橋段;密碼需 ≥10 字含字母+數字,**寫小抄照打** |
| 家教 | 用種子帳號 **`tutor_zhang`(張家豪)** | 已有 5.0 評分與一個進行中媒合,dashboard 內容豐富;密碼從 §2 的 log 取得 |

種子家教 **張家豪** `max_students=4`、目前 1 個在學媒合,容量充足,可再接現場新邀約。瀏覽搜尋頁時,張家豪(5.0)、黃柏翰(約 4.25)都有評分可展示雷達圖;李佳穎無評價(正好示範「無評價 tutor 排在最後」)。

`psql` 連線:

```bash
psql -h 127.0.0.1 -p 41432 -U <DB_USER> -d <DB_NAME>
# DB_USER / DB_NAME 見 repo 根目錄 .env;密碼見 secrets/db_password.txt
```

---

## 4. 資料庫深掘 SQL 腳本

存成 `demo.sql`。主講 **D**(操作 psql)+ **E**(先開 Access ER 圖、輔助講解)。以下佔位符請在彩排時填真實值:`<TID>`= 張家豪的 `tutor_id`;step 3 的 user id 改成種子資料中真實存在的兩個 user。

### 步驟 1 — ER 圖與表清單

E 先開 `tutor-platform-api/data/tutoring.accdb` 的 relationship view(課程要求的產出),一句帶過。再回 psql:

```sql
\dt                 -- 19 張表:14 張業務表 + 5 張基礎設施表
\d tutor_subjects   -- 指出 composite PK (tutor_id, subject_id) —— 解多對多並帶 per-subject 費率
\d matches          -- 指出 partial unique index idx_matches_one_active
```

> 講解:「`tutor_subjects` 用複合主鍵解 tutors↔subjects 的多對多,還順帶記每科時薪。`matches` 上有個 partial unique index —— **只在非終態時生效**,從資料庫層擋掉重複媒合;終態(ended/cancelled/rejected)允許同組合再次媒合。」

### 步驟 2 — CHECK 約束擋下髒資料

```sql
INSERT INTO subjects (subject_name, category) VALUES ('占星學', 'astrology');
-- ERROR: violates check constraint "chk_subject_category"
```

> 講解:「`category` 只允許 math / science / lang / other。約束在資料庫層,不論 API 還是直接連線都擋得住。」(INSERT 被拒,不會留下髒資料)

### 步驟 3 — Trigger 即時生效:對話 ID 自動排序

```sql
-- 先看現有對話組合,挑一組「目前沒有對話」的 user 配對代入下面
SELECT user_a_id, user_b_id FROM conversations ORDER BY 1, 2;

BEGIN;
INSERT INTO conversations (user_a_id, user_b_id) VALUES (9, 4);  -- 故意大的放前面
SELECT conversation_id, user_a_id, user_b_id
FROM conversations ORDER BY conversation_id DESC LIMIT 1;
-- 結果:user_a_id=4, user_b_id=9 —— trg_conversations_order_pair 已自動交換
ROLLBACK;                                                        -- 不留髒資料
```

> 講解:「`fn_conversations_order_pair` 這個 BEFORE INSERT trigger 自動把小的 user id 排到前面,搭配 `(user_a_id, user_b_id)` 唯一索引,保證任兩人之間只有一條對話。若代入的配對已有對話會觸發唯一鍵衝突 —— 換一組沒對話的就好。」

### 步驟 4 — 刻意的反正規化 + trigger 回填

```sql
SELECT match_id, student_id, parent_user_id, status FROM matches ORDER BY match_id LIMIT 5;
```

> 講解:「`matches.parent_user_id` 是從 `students` 複製來的 —— **刻意的反正規化**,讓權限檢查不必每次 JOIN。寫入時由 `trg_matches_set_parent` 自動回填;家長若變更,`trg_students_propagate_parent` 會同步到所有相關媒合。這是『正規化 vs 查詢效能』的權衡。」

### 步驟 5 — Materialized View 與刷新策略 ★ 高潮

```sql
SELECT tutor_id, review_count, ROUND(avg_rating::numeric, 2) AS avg_rating
FROM v_tutor_ratings ORDER BY tutor_id;
```

> 講解:「`v_tutor_ratings` 是 **materialized view** —— 把每位家教的評分聚合**物化儲存**,tutor 列表頁讀取變成單列查詢,不必每次跑聚合子查詢。」
>
> **關鍵(這是強過 trigger 的 SQL 觀念):** 「它**不是**每次寫入就刷新 —— 那會在寫入交易中持有 MV 的排他鎖、拖慢併發寫入。我們改用一個**每 30 秒**跑一次的背景任務 `REFRESH MATERIALIZED VIEW CONCURRENTLY`。代價是評分有最多 30 秒的延遲,換來寫入路徑不被鎖卡住 —— 這是**新鮮度 vs 寫入併發**的工程取捨。`CONCURRENTLY` 不鎖讀取,但需要 `tutor_id` 上的唯一索引。」

可現場示範刷新(承 Part A §7 家長剛送出的評價):

```sql
-- 家長剛在 app 送出新評價,但背景任務還沒到 30 秒 → MV 仍是舊值
REFRESH MATERIALIZED VIEW CONCURRENTLY v_tutor_ratings;   -- 手動刷新
SELECT tutor_id, review_count, ROUND(avg_rating::numeric, 2) AS avg_rating
FROM v_tutor_ratings ORDER BY tutor_id;                   -- review_count 增加了
```

### 步驟 6 — 多表 JOIN(搜尋頁背後的查詢)

```sql
SELECT u.display_name, t.university, s.subject_name,
       ts.hourly_rate, vr.avg_rating, vr.review_count
FROM tutors t
JOIN users u           ON u.user_id    = t.user_id
JOIN tutor_subjects ts ON ts.tutor_id  = t.tutor_id
JOIN subjects s        ON s.subject_id = ts.subject_id
LEFT JOIN v_tutor_ratings vr ON vr.tutor_id = t.tutor_id
WHERE s.subject_name = '數學'
  AND ts.hourly_rate BETWEEN 600 AND 1000
ORDER BY vr.avg_rating DESC NULLS LAST;
```

> 講解:「這就是家長搜尋頁背後的查詢 —— 跨 users、tutors、tutor_subjects、subjects 四表,再 LEFT JOIN materialized view 取評分。沒評價的家教用 `NULLS LAST` 排到最後。」

### 步驟 7 — 稽核軌跡:session_edit_logs

承 Part A 家教編輯課程記錄後:

```sql
SELECT sel.log_id, sel.field_name, sel.old_value, sel.new_value, sel.edited_at
FROM session_edit_logs sel
ORDER BY sel.log_id DESC LIMIT 10;
```

> 講解:「家教每改一個課程記錄欄位,後端就在 `session_edit_logs` 補一列 —— 欄位名、舊值、新值、時間。Google Docs 式的逐欄稽核軌跡。」

### 步驟 8 — EXPLAIN ANALYZE 證明索引生效

```sql
EXPLAIN ANALYZE
SELECT * FROM tutor_subjects WHERE subject_id = 1;
-- 指出走 idx_tutor_subjects_subject 索引,而非 Seq Scan
```

---

## 5. Q&A 預備

- **「為什麼 `matches.parent_user_id` 重複存了 `students` 的資料?」**
  → 刻意反正規化換查詢效能;`trg_matches_set_parent` / `trg_students_propagate_parent` 維持一致性。
- **「materialized view 和一般 view 差在哪?為什麼用、又為什麼不每次刷新?」**
  → MV 把聚合結果物化,讀取近乎 O(1);不每次寫入就刷新是為了不在寫入交易中持有排他鎖,改由每 30 秒的背景任務 `REFRESH ... CONCURRENTLY`,以最多 30 秒延遲換寫入併發。
- **「schema 正規化到第幾正規化?」**
  → 業務表達 3NF;`parent_user_id` 是唯一刻意的例外,理由如上。
- **「為什麼有些外鍵 CASCADE、有些 RESTRICT、有些 SET NULL?」**
  → 帳號附屬資料 CASCADE(刪帳號連帶清除);計費/法律記錄(`matches`)RESTRICT 防誤刪;稽核記錄(`audit_log`)SET NULL,讓記錄在帳號刪除後仍存活。
- **「重複媒合怎麼防?」**
  → 應用層檢查 + 資料庫層 partial unique index(`idx_matches_one_active`)雙保險,後者擋掉 TOCTOU race。
- **「為什麼用 PostgreSQL 不用 Access?」**
  → Access 是課程要求的原型;PostgreSQL 支援 trigger、materialized view、partial index、TIMESTAMPTZ、容器化部署,可在任何有 Docker 的機器上重現。
- **「重複送出邀約會建出兩筆媒合嗎?」**
  → 不會。`POST /api/matches` 帶 `Idempotency-Key`,由 `idempotency_keys` 表去重。

---

# Part A — 實體現場 demo(約 20 分鐘)

## 6. Part A — 時間總表與分工

| 時段 | 段落 | 主講 | 重點 |
|---|---|---|---|
| 0:00–1:30 | 開場 + 架構 | **A**(技術長) | 定位、四程序架構、Access→PostgreSQL 遷移 |
| 1:30–6:30 | 產品實況:家長流程 | **B** | 現場註冊家長 → 新增小孩 → 搜尋篩選 → 雷達圖 → 發訊息 → 送出邀約 |
| 6:30–11:00 | 產品實況:家教流程 + 課程編輯記錄 | **C** | 接受邀約 → 確認試教 → 記課程 → **編輯課程(稽核軌跡)** → 記成績 → 結束媒合 |
| 11:00–12:30 | 評價 + 統計 | **C** | 三方互評、收入/支出圖、學生進步折線圖 |
| 12:30–18:30 | **資料庫深掘(live psql)** | **D + E** | §4 步驟 1–8 |
| 18:30–19:30 | Access 對照 + 收尾 | **A** | Access relationship view、已知限制、未來延伸 |
| 19:30–20:30 | Q&A 緩衝 | 全員 | —— |

**分工理由:** B、C 各 demo 自己負責的前端頁面;D、E 主講資料庫段(學資料庫的兩位,對應其評分);A 負責開場、架構、收尾。五人皆有發言,覆蓋小組評分要求。

## 7. Part A — 逐段腳本

### ① 開場 + 架構 — A,1.5 分

- 一句話定位:「TMRP 是家教版的 104 —— 家長搜尋家教、媒合、上課記錄、結束後三方互評。」
- 架構圖:Nginx → FastAPI → PostgreSQL,外加 Huey worker。所有 API 回應採統一信封 `{success, data, message}`(若評審追問,可在瀏覽器開發者工具的 Network 分頁即時佐證)。
- **遷移故事(SQL 課必講):** 「資料庫先在 MS Access 建原型滿足課程要求,再遷移到 PostgreSQL 16 —— 同一套 schema 設計、兩種實作,待會兩邊都會看到。」

### ② 家長流程 — B,5 分

1. **現場註冊**一個家長帳號(照小抄打密碼)、登入。
2. 新增一個小孩(學校、年級、目標學校)。
3. 進搜尋頁:用科目(數學)+ 時薪區間 + 最低評分篩選。指出張家豪(5.0)、黃柏翰有評分,李佳穎無評分排最後。
4. 點 **張家豪** → 展示**雷達圖**(四維評分)、可預約時段、容量(在學/上限)。
5. 「發送訊息」開啟對話、送一則訊息。
6. 「送出邀約」:選張家豪、勾試教、填邀約訊息、送出。
   > 鋪陳台詞:「這張邀約等一下會在資料庫看到,而且有個 `parent_user_id` 欄位是 trigger 自動填的。」

### ③ 家教流程 + 課程編輯記錄 — C,4.5 分

1. 切到家教瀏覽器,用 §2 取得的密碼登入 **tutor_zhang(張家豪)**;dashboard 已出現新邀約。
2. 開邀約 → 接受。因帶試教,媒合進入 `trial`。
3. 確認試教 → 媒合轉 `active`。
4. 記一筆課程記錄(日期、時數、內容、作業),勾**對家長可見**。
5. **編輯**剛才那筆課程(改一下內容或時數)→ 開「編輯歷史」,展示逐欄記錄的舊值/新值。
   > 鋪陳台詞:「每改一欄,後端就往 `session_edit_logs` 補一列 —— 待會在資料庫直接看這張稽核表。」
6. 記一筆考試成績。
7. 結束媒合:家教按 `terminate` → 切回家長瀏覽器按 `agree_terminate` → 媒合轉 `ended`。
   > 鋪陳台詞:「pending→trial→active→ended 的狀態流轉,合法轉換與權限由後端狀態機強制,資料庫層另有 CHECK 約束擋非法 status。」

### ④ 評價 + 統計 — C,1.5 分

1. 家長寫 parent→tutor 評價(這筆會用在 §4 步驟 5 的 MV 示範);家教寫 tutor→student、tutor→parent 評價。
2. 秀收入長條圖(月/學生/科目切換)、支出圖、學生進步折線圖。
   > 鋪陳台詞:「家長剛送出的評價,等一下會看到它如何反映到 materialized view —— 以及為什麼不是『立刻』。」

### ⑤ 資料庫深掘 — D + E,6 分 ★ 全場高潮

照 [§4](#4-資料庫深掘-sql-腳本) 步驟 1–8 走(時間緊則步驟 8 可略)。步驟 5 的 MV 刷新示範直接呼應 ④ 家長剛送出的評價。

### ⑥ Access 對照 + 收尾 — A,1 分

- Access relationship view 與 live PostgreSQL 並排:「同一套 schema 設計、兩種實作。」
- 誠實講已知限制:聊天為輪詢非 WebSocket、單節點部署、CSV import/export 目前同步執行。
- 一句未來延伸帶過(profile 照片、即時通知)。

## 8. Part A — 風險預案

| 風險 | 預案 |
|---|---|
| docker / 投影出包 | 直接播**備案錄影**。 |
| `/seed` 跳過、沒灌進資料 | 冪等守衛:資料庫已有任何非 admin 使用者就跳過。務必 `DEBUG=false`(否則開機自動建 demo 帳號觸發跳過),且 seed 前別先註冊帳號。需重灌請用後台「清空資料庫」兩步驟流程。 |
| 找不到種子帳號密碼 | `docker compose logs api | Select-String "SEED CREDENTIALS" -Context 0,7`;彩排時就抄上小抄。 |
| 現場註冊密碼被拒 | 政策 ≥10 字、含字母+數字;密碼寫小抄照打,彩排用同一組。 |
| `psql` 連不上 | 確認跑的是含 override 的 compose(DB 綁 41432);密碼取自 `secrets/db_password.txt`。 |
| 統計圖一直轉圈 | 確認 worker 容器 healthy;彩排時先點過一次。 |
| `terminate` 卡住 | 要**對方**按 `agree_terminate`;兩瀏覽器並排,別反覆登入。 |
| 步驟 3 對話 INSERT 觸發唯一鍵衝突 | 代入的配對已有對話 —— 先 `SELECT ... FROM conversations` 挑一組沒對話的;已用 `ROLLBACK` 包住不留髒資料。 |
| 步驟 5 MV 看起來沒變 | 正常 —— 背景任務每 30 秒才刷新一次。照腳本手動 `REFRESH MATERIALIZED VIEW CONCURRENTLY` 即可,並把「為何不即時刷新」當賣點講。 |
| JWT 5 分鐘過期 | 前端自動 refresh,不影響;不用處理。 |
| trigger/MV 名稱與腳本不符 | 彩排時用 §1 的兩條核對 SQL 確認。 |

---

# Part B — YouTube 介紹影片

錄影沒有現場風險,可重錄、可剪接、時間不限,並且是一份作品集。建議總長 **20–25 分鐘**,以 YouTube 章節(章節時間戳)切分,讓觀眾跳看。比現場版多出「資料庫設計總覽」與「工程實踐」兩個可以講深的章節。

## 9. Part B — 影片規格與章節總表

| 規格 | 建議 |
|---|---|
| 解析度 / FPS | 1080p / 30fps;螢幕錄製字級放大,程式碼/SQL 區域再額外放大 |
| 旁白 | 事先寫逐字稿;一章一段、分段錄,NG 可單章重錄 |
| 章節 | 在 YouTube 說明欄放時間戳,自動形成可跳轉章節 |
| 收音 | 安靜環境;旁白與螢幕操作可分開錄再對齊 |

| # | 章節 | 約時長 | 主講 |
|---|---|---|---|
| 0 | 片頭與專案簡介 | 1:30 | A |
| 1 | 系統架構總覽 | 2:30 | A |
| 2 | 資料庫設計總覽 | 4:00 | D + E |
| 3 | 家長視角實作演示 | 4:00 | B |
| 4 | 家教視角實作演示 | 4:00 | C |
| 5 | 評價與統計 | 2:00 | C |
| 6 | 掀開引擎蓋:SQL 實戰 | 4:30 | D + E |
| 7 | 工程實踐與安全性 | 2:30 | A |
| 8 | 已知限制與未來展望 | 1:00 | A |
| 9 | 結語 | 0:30 | 全員 |
| | **合計** | **約 26 分** | |

## 10. Part B — 逐章腳本

### 第 0 章 — 片頭與專案簡介(A)
- 片名卡:TMRP — Tutor Matching and Rating Platform。
- 一句定位 + 課程脈絡:大學 SQL 課程期末專案、五人小組、Access 原型 → PostgreSQL。
- 預告本片會走過的內容(對應章節)。

### 第 1 章 — 系統架構總覽(A)
- 螢幕放 `docs/architecture.md` 的 C4 容器圖。
- 講四程序:Nginx(web)→ FastAPI(api)→ PostgreSQL(db),外加 Huey worker。
- 一句帶過 DDD bounded contexts 與三層架構(細節留到第 7 章)。

### 第 2 章 — 資料庫設計總覽(D + E)★ SQL 課重點
- 開 Access `tutoring.accdb` 的 relationship view —— 課程要求的產出。
- 開 `docs/database-schema.md` 的 Mermaid ER 圖,講 19 張表如何分組(身分、教學目錄、訊息、媒合、教學記錄、評價、基礎設施)。
- 正規化:`tutor_subjects` 解多對多並帶 per-subject 費率(複合主鍵);`conversations` 一對使用者一列。
- 型別選擇:金額用 `NUMERIC` 避免浮點誤差、時間一律 `TIMESTAMPTZ`、`tutor_availability` 用 `TIME`(每週循環)。
- 一句刻意反正規化:`matches.parent_user_id`(細節留到第 6 章)。

### 第 3 章 — 家長視角實作演示(B)
- 對照 Part A §7 ②:註冊家長 → 新增小孩 → 搜尋篩選 → 張家豪雷達圖 → 發訊息 → 送出邀約。
- 錄影版可放慢、加說明字幕,把每個畫面講清楚。

### 第 4 章 — 家教視角實作演示(C)
- 對照 Part A §7 ③:登入家教 → 接受邀約 → 確認試教 → 記課程 → **編輯課程並展示稽核軌跡** → 記成績 → 結束媒合。
- 旁白點出 match 狀態機:pending → trial → active → ended。

### 第 5 章 — 評價與統計(C)
- 三方互評(parent→tutor、tutor→student、tutor→parent)。
- 收入/支出長條圖、學生進步折線圖;一句帶過統計是 Huey 非同步任務、前端輪詢 task 狀態。

### 第 6 章 — 掀開引擎蓋:SQL 實戰(D + E)★ 全片高潮
- live psql,照 [§4](#4-資料庫深掘-sql-腳本) 步驟 2–8 全跑(錄影可全做,含步驟 8 EXPLAIN ANALYZE)。
- 步驟 5 的 MV:錄影版可**真的等 30 秒**讓背景任務自動刷新,或剪接跳過,把「新鮮度 vs 寫入併發」的取捨講透。
- 此章是這支影片最該講深、最能展現 SQL 能力的部分。

### 第 7 章 — 工程實踐與安全性(A)
- 現場版沒時間、錄影版可以講:後端 DDD bounded contexts、match 狀態機是純邏輯可單元測試、middleware 管線(CSRF、rate limit、body size、security headers)。
- 安全:bcrypt 雜湊、JWT 放 HttpOnly cookie、refresh token 黑名單、`password_history` 防重用、Docker secrets。
- 一句帶過 pytest 測試套件(狀態機、SQL injection 等)。

### 第 8 章 — 已知限制與未來展望(A)
- 誠實說限制:聊天輪詢非 WebSocket、單節點、CSV import/export 同步執行。
- 未來:即時通知、profile 照片、Access 月報表。

### 第 9 章 — 結語(全員)
- 五位成員各一句(或字幕)感謝;放 repo / 文件指引。

## 11. Part B — 錄製與後製建議

- **工具:** OBS Studio 螢幕錄製;旁白可用手機/麥克風單獨錄再於剪輯軟體對齊。
- **分章錄:** 一章錄成一個檔,NG 只需重錄該章 —— 這是錄影相對現場最大的優勢,善用它。
- **可讀性:** 程式碼/SQL/終端畫面務必放大;關鍵行用框選或縮放強調。
- **節奏:** 操作畫面比現場稍慢、留白給旁白;冗長等待(docker build、灌種子)直接剪掉或加速。
- **章節時間戳:** 完成後把每章起始時間寫進 YouTube 說明欄(`0:00 片頭` 格式),自動生成可跳轉章節。
- **字幕:** 至少上中文字幕;專有名詞(materialized view、trigger、bounded context)出現時可加說明小卡。
- **正確性:** 旁白稿凡提到 trigger / MV,以本文件 [§1](#1-已驗證的-schema-事實) 或已更新的 `database-schema.md` / `architecture.md` 為準。

---

*相關文件:`project-spec.md` §12、`architecture.md`、`database-schema.md`。*
