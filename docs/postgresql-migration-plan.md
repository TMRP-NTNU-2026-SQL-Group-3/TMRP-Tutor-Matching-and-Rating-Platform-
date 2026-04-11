# TMRP 資料庫遷移規劃書：MS Access → PostgreSQL

> **版本**：v1.0  
> **日期**：2026-04-11  
> **範圍**：tutor-platform-api 後端全面改用 PostgreSQL

---

## 目錄

1. [現況分析](#1-現況分析)
2. [遷移動機與效益](#2-遷移動機與效益)
3. [資料型別對照表](#3-資料型別對照表)
4. [SQL 語法差異對照表](#4-sql-語法差異對照表)
5. [需修改的檔案清單](#5-需修改的檔案清單)
6. [各階段實作細節](#6-各階段實作細節)
7. [新版 Schema（PostgreSQL DDL）](#7-新版-schemapostgresql-ddl)
8. [實作順序與相依關係](#8-實作順序與相依關係)
9. [測試計畫](#9-測試計畫)
10. [風險與注意事項](#10-風險與注意事項)

---

## 1. 現況分析

### 1.1 目前架構

| 層級 | 技術 |
|------|------|
| 前端 | Vue 3 + Vite + Tailwind CSS + Pinia |
| 後端 | Python FastAPI + Uvicorn |
| 資料庫 | MS Access (.accdb) 透過 pyodbc ODBC 連線 |
| 任務佇列 | Huey + SQLite |
| 驗證 | JWT (python-jose) + bcrypt |

### 1.2 資料庫存取方式

- **無 ORM**，全部使用原生 SQL + 參數化查詢（`?` 佔位符）
- **Repository Pattern**：`BaseRepository` 提供 `fetch_one`、`fetch_all`、`execute`、`execute_returning_id`、`safe_update`、`fetch_paginated` 等通用方法
- **交易管理**：自製 `transaction()` 上下文管理器（`database_tx.py`）
- **連線管理**：每次請求建立新連線，請求結束關閉（`get_db()` 依賴注入）

### 1.3 MS Access 特有機制（需移除/替換）

| 機制 | 說明 | 所在檔案 |
|------|------|----------|
| VBScript + ADOX | 建立 .accdb 資料庫檔案 | `init_db.py:389-416` |
| DAO COM | 設定欄位預設值（Access ODBC 不支援 DEFAULT） | `init_db.py:438-466` |
| `AUTOINCREMENT` | 主鍵自動遞增 | `init_db.py` 全部 13 張表 |
| `SELECT @@IDENTITY` | 取得最後插入的自動 ID | `base.py:82`、`auth_repo.py:49`、`message_repo.py:77`、`seed/generator.py:30` |
| `SELECT TOP N` | 限制結果筆數（無 LIMIT/OFFSET） | `base.py:109`、`scheduled.py:18` |
| `Now()` | 資料庫端取得當前時間 | 所有 repository 的 INSERT/UPDATE（共 20+ 處） |
| `IIF()` | 條件表達式 | `message_repo.py:11-12`、`stats_repo.py:16-17,52-53` |
| `YEAR()`/`MONTH()` | 日期函式 | `stats_repo.py:22-23,41-42,59-60,82-83` |
| `BIT` 型別（-1/0） | 布林值表示法 | `access_bits.py` 全部、10+ 個使用點 |
| `MEMO` | 長文字型別 | `init_db.py` 全部 DDL |
| `CURRENCY` | 貨幣型別 | `init_db.py:99,152,156,157` |
| `[column]` 方括號引用 | 避免保留字衝突 | `columns.py:20-22`、`base.py:36` |
| LIKE 通配符轉義 `[%]` `[_]` `[[]` | Access 特有語法 | `tutor_repo.py:34` |
| 多表 JOIN 強制括號 `(((A JOIN B) JOIN C)...)` | Access SQL 要求 | `match_repo.py`、`session_repo.py`、`stats_repo.py` 等 |

### 1.4 現有資料表（13 張）

| # | 表名 | 說明 | 主鍵 |
|---|------|------|------|
| 1 | Users | 使用者帳號 | user_id |
| 2 | Tutors | 家教師個人檔案 | tutor_id |
| 3 | Students | 學生（家長的孩子） | student_id |
| 4 | Subjects | 科目目錄 | subject_id |
| 5 | Tutor_Subjects | 家教可教科目與費率 | (tutor_id, subject_id) |
| 6 | Tutor_Availability | 可用時段 | availability_id |
| 7 | Conversations | 對話串 | conversation_id |
| 8 | Messages | 個別訊息 | message_id |
| 9 | Matches | 配對關係 | match_id |
| 10 | Sessions | 上課記錄 | session_id |
| 11 | Session_Edit_Logs | 編輯稽核紀錄 | log_id |
| 12 | Exams | 學生考試成績 | exam_id |
| 13 | Reviews | 三向評價 | review_id |

---

## 2. 遷移動機與效益

### 現有問題

| 問題 | 說明 |
|------|------|
| 平台鎖定 | MS Access 僅限 Windows，需安裝 Access Database Engine |
| 併發瓶頸 | 檔案級鎖定，需指數退避重試機制 |
| 無連線池 | 每次請求開關連線，效能低落 |
| 語法限制 | 無 LIMIT/OFFSET、無 DEFAULT 子句、JOIN 需括號 |
| 部署限制 | 無法容器化（Docker），無法部署至 Linux/雲端 |
| 維護成本 | VBScript/DAO COM 等額外依賴 |

### 遷移效益

| 效益 | 說明 |
|------|------|
| 跨平台 | Windows / Linux / macOS / Docker 皆可運行 |
| 高併發 | 行級鎖定 + 連線池，無需重試機制 |
| 標準 SQL | 支援 LIMIT/OFFSET、DEFAULT、RETURNING、CTE 等 |
| 生態系豐富 | pgAdmin、Alembic、pg_dump 等工具 |
| 雲端就緒 | AWS RDS、Render、Supabase 等皆支援 |
| 效能提升 | 移除重試邏輯、連線池複用、原生布林型別 |

---

## 3. 資料型別對照表

| MS Access | PostgreSQL | 說明 |
|-----------|------------|------|
| `AUTOINCREMENT` | `SERIAL` | 自動遞增主鍵（等同 `INTEGER` + `SEQUENCE`） |
| `LONG` | `INTEGER` | 32 位元整數 |
| `SHORT` | `SMALLINT` | 16 位元整數 |
| `DOUBLE` | `DOUBLE PRECISION` | 雙精度浮點數 |
| `CURRENCY` | `NUMERIC(12,2)` | 固定精度十進位（家教費率足夠用 12,2） |
| `BIT` | `BOOLEAN` | 原生布林（`TRUE`/`FALSE`） |
| `VARCHAR(n)` | `VARCHAR(n)` | 無變動 |
| `MEMO` | `TEXT` | 無限長度文字 |
| `DATETIME` | `TIMESTAMPTZ` | 含時區的時間戳（建議改用帶時區版本） |

---

## 4. SQL 語法差異對照表

### 4.1 函式與表達式

| 功能 | MS Access | PostgreSQL |
|------|-----------|------------|
| 當前時間 | `Now()` | `NOW()` (相容) 或 `CURRENT_TIMESTAMP` |
| 條件表達式 | `IIF(cond, a, b)` | `CASE WHEN cond THEN a ELSE b END` |
| NULL 預設值 | `IIF(x IS NULL, 0, x)` | `COALESCE(x, 0)` |
| 取年 | `YEAR(date)` | `EXTRACT(YEAR FROM date)` |
| 取月 | `MONTH(date)` | `EXTRACT(MONTH FROM date)` |
| 取最後插入 ID | `SELECT @@IDENTITY` | `INSERT ... RETURNING id` |
| 限制筆數 | `SELECT TOP N ...` | `SELECT ... LIMIT N` |
| 分頁 | `TOP N` + Python 切割 | `LIMIT N OFFSET M` |
| 佔位符 | `?` | `%s`（psycopg2）或 `$1`（asyncpg） |

### 4.2 DDL

| 功能 | MS Access | PostgreSQL |
|------|-----------|------------|
| 自動遞增 | `AUTOINCREMENT` | `SERIAL` |
| 預設值 | 需透過 DAO COM | 直接 `DEFAULT NOW()` |
| CHECK 約束 | `CONSTRAINT ck_x CHECK(...)` | 相同語法 |
| 欄位引用 | `[column]` 方括號 | `"column"` 雙引號（多數情況不需引用） |

### 4.3 LIKE 轉義

| MS Access | PostgreSQL |
|-----------|------------|
| `[%]` 轉義百分號 | `\%`（搭配 `ESCAPE '\'`） |
| `[_]` 轉義底線 | `\_`（搭配 `ESCAPE '\'`） |
| `[[]` 轉義左方括號 | 不需要（`[` 非特殊字元） |

### 4.4 JOIN 語法

MS Access 要求多表 JOIN 加括號：
```sql
-- MS Access
FROM (((Matches m
INNER JOIN Subjects s ON m.subject_id = s.subject_id)
INNER JOIN Students st ON m.student_id = st.student_id)
INNER JOIN Tutors t ON m.tutor_id = t.tutor_id)
INNER JOIN Users u ON t.user_id = u.user_id

-- PostgreSQL（標準 SQL）
FROM Matches m
INNER JOIN Subjects s ON m.subject_id = s.subject_id
INNER JOIN Students st ON m.student_id = st.student_id
INNER JOIN Tutors t ON m.tutor_id = t.tutor_id
INNER JOIN Users u ON t.user_id = u.user_id
```

---

## 5. 需修改的檔案清單

### 5.1 核心資料庫層（完全重寫）

| 檔案 | 修改類型 | 說明 |
|------|----------|------|
| `app/config.py` | **重寫** | `access_db_path` → PostgreSQL 連線參數（host/port/dbname/user/password）或 `DATABASE_URL` |
| `app/database.py` | **重寫** | pyodbc → psycopg2 連線池，移除重試機制 |
| `app/database_tx.py` | **重寫** | 適配 psycopg2 交易管理（更簡潔） |
| `app/init_db.py` | **重寫** | 移除 VBScript/DAO，改用標準 PostgreSQL DDL（含 DEFAULT） |

### 5.2 Repository 層（SQL 語法修改）

| 檔案 | 修改點數 | 主要變更 |
|------|----------|----------|
| `app/repositories/base.py` | **6 處** | `@@IDENTITY` → `RETURNING`、`TOP N` → `LIMIT/OFFSET`、`[col]` → `col`、`?` → `%s` |
| `app/repositories/auth_repo.py` | **2 處** | `@@IDENTITY` → `RETURNING`、移除 `?` → `%s` |
| `app/repositories/tutor_repo.py` | **3 處** | LIKE 轉義改用 `\` 風格、移除 `to_access_bit` |
| `app/repositories/match_repo.py` | **5 處** | `Now()` 保留、`to_access_bit` → 直接用 bool、移除 JOIN 括號 |
| `app/repositories/session_repo.py` | **4 處** | `Now()`、`to_access_bit`、`?` → `%s` |
| `app/repositories/review_repo.py` | **2 處** | `Now()`、`?` → `%s` |
| `app/repositories/message_repo.py` | **5 處** | `IIF` → `CASE WHEN`、`@@IDENTITY` → `RETURNING`、`Now()`、移除 JOIN 括號 |
| `app/repositories/stats_repo.py` | **8 處** | `IIF` → `COALESCE`、`YEAR()`/`MONTH()` → `EXTRACT()`、移除 JOIN 括號 |
| `app/repositories/exam_repo.py` | **3 處** | `to_access_bit`、`Now()`、`?` → `%s` |
| `app/repositories/student_repo.py` | **1 處** | `?` → `%s` |

### 5.3 工具模組

| 檔案 | 修改類型 | 說明 |
|------|----------|------|
| `app/utils/access_bits.py` | **刪除** | PostgreSQL 原生支援 `BOOLEAN`，不需轉換 |
| `app/utils/columns.py` | **修改** | `bracket_columns()` 改用雙引號或移除引用；`coerce_csv_value()` 移除 `-1`/`0` 布林邏輯 |

### 5.4 任務模組

| 檔案 | 修改類型 | 說明 |
|------|----------|------|
| `app/tasks/scheduled.py` | **修改** | 移除 `to_access_bit`、`SELECT TOP 1` → `SELECT ... LIMIT 1`、`get_connection()` 改用連線池 |
| `app/tasks/import_export.py` | **修改** | 移除 `bracket_columns`/`coerce_csv_value` 的 Access 邏輯 |
| `app/tasks/stats_tasks.py` | **微調** | `get_connection()` 改用連線池取得連線 |
| `app/tasks/seed_tasks.py` | **微調** | 同上 |
| `app/worker.py` | **不變** | Huey 仍用 SQLite 作為任務佇列（獨立於主資料庫） |

### 5.5 路由層

| 檔案 | 修改說明 |
|------|----------|
| `app/routers/sessions.py` | 移除 `from_access_bit`/`to_access_bit` import 與用法（5 處） |
| `app/routers/matches.py` | 移除 `from_access_bit` import 與用法（2 處） |
| `app/routers/reviews.py` | 移除 `from_access_bit` import 與用法（2 處） |
| `app/routers/exams.py` | 移除 `to_access_bit` import 與用法（2 處） |
| `app/routers/admin.py` | 修改 `bracket_columns`/`coerce_csv_value` 用法（3 處） |

### 5.6 種子資料 & 環境設定

| 檔案 | 修改類型 | 說明 |
|------|----------|------|
| `seed/generator.py` | **修改** | 移除 `to_access_bit`、`@@IDENTITY` → `RETURNING`、pyodbc 型別提示改為 psycopg2 |
| `.env` | **重寫** | `ACCESS_DB_PATH` → `DATABASE_URL` |
| `.env.example` | **重寫** | 同上 |
| `requirements.txt` | **修改** | `pyodbc` → `psycopg2-binary` |
| `start.bat` | **修改** | 移除 Access 驅動檢查與 .accdb 檔案建立邏輯 |

### 5.7 可刪除的檔案

| 檔案 | 原因 |
|------|------|
| `app/utils/access_bits.py` | Access BIT 轉換不再需要 |
| `data/tutoring.accdb` | Access 資料庫檔案 |

---

## 6. 各階段實作細節

### 第一階段：基礎設施（config + 連線 + 交易）

#### 6.1.1 `app/config.py` — 連線設定

**變更前**：
```python
access_db_path: str = "data/tutoring.accdb"
```

**變更後**：
```python
database_url: str = "postgresql://tmrp:tmrp@localhost:5432/tmrp"
db_pool_min: int = 2
db_pool_max: int = 10
```

`.env` 對應變更：
```env
# 舊
ACCESS_DB_PATH=data/tutoring.accdb

# 新
DATABASE_URL=postgresql://tmrp:tmrp@localhost:5432/tmrp
```

#### 6.1.2 `app/database.py` — 連線池

**變更前**：pyodbc 單連線 + 重試機制（65 行）

**變更後**：psycopg2 連線池（約 45 行）

```python
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from app.config import settings

# 應用啟動時建立連線池
_pool: pool.ThreadedConnectionPool | None = None

def init_pool():
    global _pool
    _pool = pool.ThreadedConnectionPool(
        minconn=settings.db_pool_min,
        maxconn=settings.db_pool_max,
        dsn=settings.database_url,
    )

def get_db():
    """FastAPI 依賴注入：從池取得連線，請求結束歸還。"""
    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)

def get_connection():
    """背景任務用：從池取得連線。呼叫者需自行 putconn()。"""
    return _pool.getconn()

def release_connection(conn):
    """歸還連線至池。"""
    _pool.putconn(conn)
```

關鍵差異：
- **移除重試機制**：PostgreSQL 使用行級鎖，不存在 Access 的檔案鎖競爭問題
- **連線池**：不再每次請求建立/關閉連線，大幅提升效能
- **移除 ODBC**：不需 Windows 專用驅動

#### 6.1.3 `app/database_tx.py` — 交易管理

**變更前**：手動管理 autocommit 旗標 + 巢狀偵測

**變更後**：利用 psycopg2 原生交易

```python
from contextlib import contextmanager

@contextmanager
def transaction(conn):
    """交易上下文管理器。成功 commit，例外 rollback。"""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
```

psycopg2 連線預設即為交易模式（autocommit=False），不需手動切換。

### 第二階段：Schema 與初始化（init_db.py）

完全重寫 `init_db.py`，移除 VBScript/DAO，改用標準 PostgreSQL DDL。
- 所有 `DEFAULT` 直接在 `CREATE TABLE` 中定義
- `SERIAL` 取代 `AUTOINCREMENT`
- `BOOLEAN` 取代 `BIT`
- `TEXT` 取代 `MEMO`
- `NUMERIC(12,2)` 取代 `CURRENCY`
- `TIMESTAMPTZ` 取代 `DATETIME`

詳見 [第 7 節](#7-新版-schemapostgresql-ddl) 的完整 DDL。

### 第三階段：BaseRepository 核心修改

#### 6.3.1 `execute_returning_id()` — 最關鍵的變更

**變更前**：
```python
def execute_returning_id(self, sql: str, params: tuple = ()) -> int:
    self.cursor.execute(sql, params)
    self.cursor.execute("SELECT @@IDENTITY")
    new_id = self.cursor.fetchone()[0]
    ...
    return new_id
```

**變更後**：
```python
def execute_returning_id(self, sql: str, params: tuple = (), id_col: str = "id") -> int:
    # 呼叫者的 SQL 需加上 RETURNING <id_col>
    self.cursor.execute(sql, params)
    new_id = self.cursor.fetchone()[0]
    ...
    return new_id
```

所有呼叫點的 INSERT 語句需加上 `RETURNING <id_column>`，例如：
```sql
-- 變更前
INSERT INTO Users (...) VALUES (...)
-- 變更後
INSERT INTO Users (...) VALUES (...) RETURNING user_id
```

#### 6.3.2 `fetch_paginated()` — 分頁邏輯

**變更前**（Access TOP N + Python 切割）：
```python
top_sql = sql.replace("SELECT ", f"SELECT TOP {top_n} ", 1)
rows = self.fetch_all(top_sql, params)
start = (page - 1) * page_size
items = rows[start : start + page_size]
```

**變更後**（PostgreSQL LIMIT/OFFSET）：
```python
offset = (page - 1) * page_size
paged_sql = f"{sql} LIMIT {page_size} OFFSET {offset}"
items = self.fetch_all(paged_sql, params)
```

#### 6.3.3 `safe_update()` — 欄位引用

**變更前**：
```python
set_clause = ", ".join(f"[{col}] = ?" for col in updates)
```

**變更後**：
```python
set_clause = ", ".join(f"{col} = %s" for col in updates)
```

#### 6.3.4 全域佔位符

整個 Repository 層的所有 SQL 語句，`?` 需全部替換為 `%s`。

### 第四階段：各 Repository SQL 語法修改

#### 6.4.1 `message_repo.py` — IIF → CASE WHEN

**變更前**：
```sql
IIF(c.user_a_id = ?, u_b.display_name, u_a.display_name) AS other_name,
IIF(c.user_a_id = ?, c.user_b_id, c.user_a_id) AS other_user_id
```

**變更後**：
```sql
CASE WHEN c.user_a_id = %s THEN u_b.display_name ELSE u_a.display_name END AS other_name,
CASE WHEN c.user_a_id = %s THEN c.user_b_id ELSE c.user_a_id END AS other_user_id
```

#### 6.4.2 `stats_repo.py` — IIF → COALESCE、日期函式

**變更前**：
```sql
IIF(SUM(se.hours) IS NULL, 0, SUM(se.hours)) AS total_hours
...
WHERE YEAR(se.session_date) = ? AND MONTH(se.session_date) = ?
```

**變更後**：
```sql
COALESCE(SUM(se.hours), 0) AS total_hours
...
WHERE EXTRACT(YEAR FROM se.session_date) = %s AND EXTRACT(MONTH FROM se.session_date) = %s
```

#### 6.4.3 `tutor_repo.py` — LIKE 轉義

**變更前**（Access 風格）：
```python
escaped = school.replace("[", "\x00").replace("]", "[]]").replace("\x00", "[[]").replace("%", "[%]").replace("_", "[_]")
conditions.append("t.university LIKE ?")
```

**變更後**（PostgreSQL 風格）：
```python
escaped = school.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
conditions.append("t.university LIKE %s ESCAPE '\\'")
```

#### 6.4.4 `match_repo.py` 等 — 移除 JOIN 括號

**變更前**：
```sql
FROM (((Matches m
INNER JOIN Subjects s ON m.subject_id = s.subject_id)
INNER JOIN Students st ON m.student_id = st.student_id)
INNER JOIN Tutors t ON m.tutor_id = t.tutor_id)
INNER JOIN Users u ON t.user_id = u.user_id
```

**變更後**：
```sql
FROM Matches m
INNER JOIN Subjects s ON m.subject_id = s.subject_id
INNER JOIN Students st ON m.student_id = st.student_id
INNER JOIN Tutors t ON m.tutor_id = t.tutor_id
INNER JOIN Users u ON t.user_id = u.user_id
```

#### 6.4.5 所有 Repository — 移除 `to_access_bit()` / `from_access_bit()`

**變更前**：
```python
want_trial_bit = to_access_bit(want_trial)
# 及
if from_access_bit(review["is_locked"]):
```

**變更後**：
```python
# 直接傳入 Python bool，psycopg2 自動轉為 PostgreSQL BOOLEAN
want_trial_bit = want_trial
# 及
if review["is_locked"]:
```

### 第五階段：路由層 & 工具模組清理

#### 6.5.1 移除所有 `access_bits` 引用

涉及的路由檔案：
- `app/routers/sessions.py`：移除 `from_access_bit`、`to_access_bit`（行 9, 95, 115）
- `app/routers/matches.py`：移除 `from_access_bit`（行 13, 200）
- `app/routers/reviews.py`：移除 `from_access_bit`（行 6, 100）
- `app/routers/exams.py`：移除 `to_access_bit`（行 92-93）

#### 6.5.2 修改 `app/utils/columns.py`

```python
# 變更前
def bracket_columns(columns: list[str]) -> str:
    return ", ".join(f"[{col}]" for col in columns)

def coerce_csv_value(val):
    if val in ('True', 'true', '1', '-1'):
        return -1   # MS Access BIT True
    if val in ('False', 'false', '0'):
        return 0
    ...

# 變更後
def quote_columns(columns: list[str]) -> str:
    """以雙引號引用欄位名稱（PostgreSQL 識別符引用方式）。"""
    return ", ".join(f'"{col}"' for col in columns)

def coerce_csv_value(val):
    if val in ('True', 'true', '1', '-1'):
        return True   # PostgreSQL 原生 BOOLEAN
    if val in ('False', 'false', '0'):
        return False
    ...
```

### 第六階段：種子資料 & 背景任務

#### 6.6.1 `seed/generator.py`

- 移除 `from app.utils.access_bits import to_access_bit`
- `TRUE = to_access_bit(True)` → `TRUE = True`
- `FALSE = to_access_bit(False)` → `FALSE = False`
- `_insert_and_get_id()` 改用 `RETURNING` 語法
- 型別提示 `pyodbc.Cursor` → 移除或改為通用型別

#### 6.6.2 `app/tasks/scheduled.py`

- 移除 `to_access_bit` import
- `SELECT TOP 1 is_locked FROM Reviews` → `SELECT is_locked FROM Reviews LIMIT 1`
- `to_access_bit(True)` / `to_access_bit(False)` → `True` / `False`
- `get_connection()` → 搭配 `release_connection()` 歸還連線

### 第七階段：環境設定 & 依賴

#### `requirements.txt`

```diff
- pyodbc==5.2.0
+ psycopg2-binary==2.9.10
```

#### `.env` / `.env.example`

```diff
- ACCESS_DB_PATH=data/tutoring.accdb
+ DATABASE_URL=postgresql://tmrp:tmrp@localhost:5432/tmrp
```

#### `start.bat`

```diff
- if not exist "data\tutoring.accdb" (
-     echo [INFO] Database not found. Initializing...
-     python -m app.database --init
+ echo [INFO] Checking database...
+ python -m app.database --init
```

---

## 7. 新版 Schema（PostgreSQL DDL）

```sql
-- ============================================
-- TMRP PostgreSQL Schema
-- ============================================

CREATE TABLE users (
    user_id       SERIAL PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(10)  NOT NULL,
    display_name  VARCHAR(50)  NOT NULL,
    phone         VARCHAR(20),
    email         VARCHAR(100),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE tutors (
    tutor_id            SERIAL PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(user_id),
    university          VARCHAR(50),
    department          VARCHAR(50),
    grade_year          SMALLINT,
    self_intro          TEXT,
    teaching_experience TEXT,
    max_students        SMALLINT     DEFAULT 5,
    show_university     BOOLEAN      DEFAULT TRUE,
    show_department     BOOLEAN      DEFAULT TRUE,
    show_grade_year     BOOLEAN      DEFAULT TRUE,
    show_hourly_rate    BOOLEAN      DEFAULT TRUE,
    show_subjects       BOOLEAN      DEFAULT TRUE
);

CREATE TABLE students (
    student_id    SERIAL PRIMARY KEY,
    parent_user_id INTEGER NOT NULL REFERENCES users(user_id),
    name          VARCHAR(50) NOT NULL,
    school        VARCHAR(50),
    grade         VARCHAR(20),
    target_school VARCHAR(50),
    parent_phone  VARCHAR(20),
    notes         TEXT
);

CREATE TABLE subjects (
    subject_id   SERIAL PRIMARY KEY,
    subject_name VARCHAR(30) NOT NULL,
    category     VARCHAR(20) NOT NULL
);

CREATE TABLE tutor_subjects (
    tutor_id    INTEGER       NOT NULL REFERENCES tutors(tutor_id),
    subject_id  INTEGER       NOT NULL REFERENCES subjects(subject_id),
    hourly_rate NUMERIC(12,2) NOT NULL,
    PRIMARY KEY (tutor_id, subject_id)
);

CREATE TABLE tutor_availability (
    availability_id SERIAL PRIMARY KEY,
    tutor_id        INTEGER   NOT NULL REFERENCES tutors(tutor_id),
    day_of_week     SMALLINT  NOT NULL CHECK (day_of_week >= 0 AND day_of_week <= 6),
    start_time      TIMESTAMPTZ NOT NULL,
    end_time        TIMESTAMPTZ NOT NULL
);

CREATE TABLE conversations (
    conversation_id SERIAL PRIMARY KEY,
    user_a_id       INTEGER     NOT NULL REFERENCES users(user_id),
    user_b_id       INTEGER     NOT NULL REFERENCES users(user_id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMPTZ
);

CREATE TABLE messages (
    message_id    SERIAL PRIMARY KEY,
    conversation_id INTEGER     NOT NULL REFERENCES conversations(conversation_id),
    sender_user_id  INTEGER     NOT NULL REFERENCES users(user_id),
    content       TEXT         NOT NULL,
    sent_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE matches (
    match_id          SERIAL PRIMARY KEY,
    tutor_id          INTEGER       NOT NULL REFERENCES tutors(tutor_id),
    student_id        INTEGER       NOT NULL REFERENCES students(student_id),
    subject_id        INTEGER       NOT NULL REFERENCES subjects(subject_id),
    status            VARCHAR(15)   NOT NULL DEFAULT 'pending',
    invite_message    TEXT,
    want_trial        BOOLEAN       DEFAULT FALSE,
    hourly_rate       NUMERIC(12,2),
    sessions_per_week SMALLINT,
    start_date        TIMESTAMPTZ,
    end_date          TIMESTAMPTZ,
    penalty_amount    NUMERIC(12,2),
    trial_price       NUMERIC(12,2),
    trial_count       SMALLINT,
    contract_notes    TEXT,
    terminated_by     INTEGER       REFERENCES users(user_id),
    termination_reason TEXT,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE sessions (
    session_id          SERIAL PRIMARY KEY,
    match_id            INTEGER       NOT NULL REFERENCES matches(match_id),
    session_date        TIMESTAMPTZ   NOT NULL,
    hours               DOUBLE PRECISION NOT NULL,
    content_summary     TEXT          NOT NULL,
    homework            TEXT,
    student_performance TEXT,
    next_plan           TEXT,
    visible_to_parent   BOOLEAN       DEFAULT FALSE,
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE session_edit_logs (
    log_id     SERIAL PRIMARY KEY,
    session_id INTEGER     NOT NULL REFERENCES sessions(session_id),
    field_name VARCHAR(50) NOT NULL,
    old_value  TEXT,
    new_value  TEXT,
    edited_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE exams (
    exam_id          SERIAL PRIMARY KEY,
    student_id       INTEGER          NOT NULL REFERENCES students(student_id),
    subject_id       INTEGER          NOT NULL REFERENCES subjects(subject_id),
    added_by_user_id INTEGER          NOT NULL REFERENCES users(user_id),
    exam_date        TIMESTAMPTZ      NOT NULL,
    exam_type        VARCHAR(20)      NOT NULL,
    score            DOUBLE PRECISION NOT NULL,
    visible_to_parent BOOLEAN         DEFAULT FALSE,
    created_at       TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

CREATE TABLE reviews (
    review_id          SERIAL PRIMARY KEY,
    match_id           INTEGER     NOT NULL REFERENCES matches(match_id),
    reviewer_user_id   INTEGER     NOT NULL REFERENCES users(user_id),
    review_type        VARCHAR(20) NOT NULL,
    rating_1           SMALLINT    NOT NULL,
    rating_2           SMALLINT    NOT NULL,
    rating_3           SMALLINT,
    rating_4           SMALLINT,
    personality_comment TEXT,
    comment            TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ,
    is_locked          BOOLEAN     DEFAULT FALSE
);

-- ============================================
-- 唯一索引
-- ============================================
CREATE UNIQUE INDEX idx_users_username      ON users (username);
CREATE UNIQUE INDEX idx_subjects_name       ON subjects (subject_name);
CREATE UNIQUE INDEX idx_tutors_user_id      ON tutors (user_id);
CREATE UNIQUE INDEX idx_conversations_pair  ON conversations (user_a_id, user_b_id);
CREATE UNIQUE INDEX idx_reviews_unique      ON reviews (match_id, reviewer_user_id, review_type);

-- ============================================
-- 效能索引
-- ============================================
CREATE INDEX idx_students_parent          ON students (parent_user_id);
CREATE INDEX idx_tutor_avail_tutor        ON tutor_availability (tutor_id);
CREATE INDEX idx_messages_conv            ON messages (conversation_id);
CREATE INDEX idx_messages_sent_at         ON messages (sent_at);
CREATE INDEX idx_matches_tutor            ON matches (tutor_id);
CREATE INDEX idx_matches_student          ON matches (student_id);
CREATE INDEX idx_matches_status           ON matches (status);
CREATE INDEX idx_sessions_match           ON sessions (match_id);
CREATE INDEX idx_exams_student            ON exams (student_id);
CREATE INDEX idx_reviews_match            ON reviews (match_id);
CREATE INDEX idx_conv_last_msg            ON conversations (last_message_at);
CREATE INDEX idx_tutor_subjects_subject   ON tutor_subjects (subject_id);
CREATE INDEX idx_sessions_created         ON sessions (created_at);
CREATE INDEX idx_matches_status_updated   ON matches (status, updated_at);
```

---

## 8. 實作順序與相依關係

```
第一階段 ─ 基礎設施（其他所有階段的前置條件）
│
├─ 1.1  requirements.txt：pyodbc → psycopg2-binary
├─ 1.2  .env / .env.example：連線字串
├─ 1.3  app/config.py：設定模型
├─ 1.4  app/database.py：連線池
└─ 1.5  app/database_tx.py：交易管理
│
▼
第二階段 ─ Schema（依賴第一階段的連線能力）
│
├─ 2.1  app/init_db.py：PostgreSQL DDL + 種子資料
└─ 2.2  驗證：建立資料庫並確認 schema 正確
│
▼
第三階段 ─ Repository 核心（依賴第一、二階段）
│
├─ 3.1  app/repositories/base.py：核心方法改寫
├─ 3.2  刪除 app/utils/access_bits.py
└─ 3.3  修改 app/utils/columns.py
│
▼
第四階段 ─ 各 Repository 平行修改（依賴第三階段的 BaseRepository）
│
├─ 4.1  auth_repo.py          ──┐
├─ 4.2  tutor_repo.py         ──┤
├─ 4.3  match_repo.py         ──┤
├─ 4.4  session_repo.py       ──┤  可平行進行
├─ 4.5  review_repo.py        ──┤
├─ 4.6  message_repo.py       ──┤
├─ 4.7  stats_repo.py         ──┤
├─ 4.8  exam_repo.py          ──┤
└─ 4.9  student_repo.py       ──┘
│
▼
第五階段 ─ 路由層清理（依賴第四階段的 Repository 完成）
│
├─ 5.1  routers/sessions.py   ──┐
├─ 5.2  routers/matches.py    ──┤  可平行進行
├─ 5.3  routers/reviews.py    ──┤
├─ 5.4  routers/exams.py      ──┤
└─ 5.5  routers/admin.py      ──┘
│
▼
第六階段 ─ 背景任務 & 種子（依賴第三、四階段）
│
├─ 6.1  tasks/scheduled.py
├─ 6.2  tasks/import_export.py
├─ 6.3  tasks/stats_tasks.py
├─ 6.4  tasks/seed_tasks.py
└─ 6.5  seed/generator.py
│
▼
第七階段 ─ 環境 & 啟動腳本
│
├─ 7.1  start.bat 更新
└─ 7.2  清理 data/tutoring.accdb
│
▼
第八階段 ─ 全面測試
```

### 預估修改量統計

| 類別 | 檔案數 | 預估影響行數 |
|------|--------|-------------|
| 完全重寫 | 4 | ~400 行 |
| 重度修改（SQL 語法） | 10 | ~300 行 |
| 輕度修改（移除 import/呼叫） | 7 | ~50 行 |
| 刪除 | 1 | -17 行 |
| 新增/修改設定 | 4 | ~20 行 |
| **總計** | **26 個檔案** | **~770 行** |

---

## 9. 測試計畫

### 9.1 Schema 驗證

- [ ] PostgreSQL 資料庫可成功建立
- [ ] 13 張表全部建立成功
- [ ] 所有索引建立成功
- [ ] 所有外鍵約束建立成功
- [ ] 所有 DEFAULT 值正確運作
- [ ] 種子科目資料寫入成功
- [ ] 管理員帳號建立成功

### 9.2 CRUD 驗證（逐 Repository 測試）

| Repository | 測試項目 |
|-----------|---------|
| AuthRepo | 註冊新使用者、帳號查詢、RETURNING 回傳正確 ID |
| TutorRepo | 搜尋（含 LIKE 關鍵字）、科目替換（交易）、可用時段替換 |
| StudentRepo | CRUD 全流程 |
| MatchRepo | 建立配對、狀態轉換、重複配對檢查 |
| SessionRepo | 新增日誌、編輯日誌（稽核記錄）、家長可見性篩選 |
| ReviewRepo | 新增評價、鎖定機制、唯一約束 |
| MessageRepo | 對話建立（含併發競態）、訊息傳送（交易） |
| ExamRepo | 新增成績、家長可見性篩選 |
| StatsRepo | 收入/支出統計（COALESCE + EXTRACT 正確性） |

### 9.3 API 端對端測試

- [ ] 使用者註冊/登入流程
- [ ] 家教搜尋（含關鍵字模糊查詢）
- [ ] 配對完整生命週期（pending → trial → active → ended）
- [ ] 訊息收發
- [ ] 上課記錄 CRUD + 編輯稽核
- [ ] 評價建立與鎖定
- [ ] 統計報表數據正確性
- [ ] CSV 匯入/匯出
- [ ] 分頁功能（LIMIT/OFFSET）

### 9.4 布林值驗證

確認所有原本使用 `to_access_bit()`/`from_access_bit()` 的地方：
- `visible_to_parent` 欄位篩選正確
- `show_*` 可見性旗標正確
- `is_locked` 鎖定判斷正確
- `want_trial` 試教判斷正確

### 9.5 前端整合測試

前端 (Vue) 不需要任何修改——API 回應格式不變。但仍需驗證：
- [ ] 所有頁面功能正常
- [ ] 布林欄位回傳值格式（`True`/`False` vs `-1`/`0`）是否影響前端判斷

---

## 10. 風險與注意事項

### 10.1 布林值序列化差異

**風險**：MS Access 的 `BIT` 透過 pyodbc 返回 `-1`/`0` 或 `True`/`False`（視驅動版本），前端可能依賴特定格式。

**解法**：PostgreSQL 的 `BOOLEAN` 透過 psycopg2 統一返回 Python `True`/`False`，FastAPI/Pydantic 序列化為 JSON `true`/`false`。這是標準行為，前端 JavaScript 直接兼容。

### 10.2 RETURNING 子句需修改所有 INSERT 語句

**風險**：遺漏任何使用 `execute_returning_id()` 的 INSERT 語句會導致錯誤。

**解法**：全域搜尋所有呼叫 `execute_returning_id` 的地方，逐一在 SQL 末尾加上 `RETURNING <id_col>`。
涉及檔案：`auth_repo.py`、`student_repo.py`、`match_repo.py`、`session_repo.py`、`review_repo.py`、`message_repo.py`、`exam_repo.py`、`seed/generator.py`

### 10.3 `Now()` 函式相容性

**低風險**：PostgreSQL 也支援 `NOW()` 函式且語法相同，此部分大量 SQL 可直接沿用。

### 10.4 前端不受影響

前端（Vue）僅與 FastAPI API 溝通，不直接接觸資料庫。只要 API 的請求/回應格式不變，前端零修改。

### 10.5 Huey 任務佇列不受影響

Huey 使用獨立的 SQLite 作為任務佇列後端（`data/huey.db`），與主資料庫無關，不需遷移。

### 10.6 PostgreSQL 本地安裝需求

開發環境需安裝 PostgreSQL（建議 15+）。可選方案：
- 本機安裝 PostgreSQL
- Docker：`docker run -d --name tmrp-pg -e POSTGRES_PASSWORD=tmrp -e POSTGRES_DB=tmrp -p 5432:5432 postgres:16`

### 10.7 既有資料遷移

若需保留 Access 中的既有資料，需撰寫一次性遷移腳本：
1. 從 Access 匯出全部 13 張表為 CSV
2. 建立 PostgreSQL schema
3. 匯入 CSV 至 PostgreSQL（注意布林值 `-1`→`true`、`0`→`false` 轉換）
4. 重設 SERIAL 序列值：`SELECT setval('tablename_id_seq', (SELECT MAX(id) FROM tablename));`

---

## 附錄 A：全域搜尋替換清單

以下為可安全使用全域搜尋替換的項目（僅限 `tutor-platform-api/` 目錄下的 `.py` 檔案）：

| # | 搜尋 | 替換為 | 範圍 | 備註 |
|---|------|--------|------|------|
| 1 | `from app.utils.access_bits import to_access_bit` | （刪除該行） | 全部 .py | 7 個檔案 |
| 2 | `from app.utils.access_bits import from_access_bit` | （刪除該行） | 全部 .py | 2 個檔案 |
| 3 | `from app.utils.access_bits import from_access_bit, to_access_bit` | （刪除該行） | 全部 .py | 1 個檔案 |
| 4 | `to_access_bit(True)` | `True` | 全部 .py | |
| 5 | `to_access_bit(False)` | `False` | 全部 .py | |
| 6 | `to_access_bit(` | （需人工檢查參數） | 全部 .py | 如 `to_access_bit(want_trial)` → `want_trial` |
| 7 | `from_access_bit(` | （需人工檢查，多數可直接移除） | 全部 .py | |
| 8 | `bracket_columns` | `quote_columns` | 全部 .py | 搭配 columns.py 函式改名 |

> **注意**：SQL 語句中的 `?` → `%s` 不可全域替換（會影響 Python 字串中的問號），需逐檔在 SQL 字串內替換。

---

## 附錄 B：psycopg2 vs asyncpg 選型

| 考量 | psycopg2 | asyncpg |
|------|----------|---------|
| 生態成熟度 | 最成熟，文件豐富 | 較新，社群較小 |
| API 風格 | DB-API 2.0（同步） | 原生 async/await |
| 佔位符 | `%s` | `$1, $2, ...` |
| 遷移成本 | **低**：與 pyodbc API 高度相似 | **高**：需改為位置參數 + async |
| 效能 | 優秀（C 擴展） | 極佳（原生 async） |
| FastAPI 整合 | 同步 DI，簡單直接 | 需 async DI |

**建議選用 `psycopg2-binary`**：遷移成本最低，API 與目前的 pyodbc 用法最接近，所有 Repository 的同步寫法無需改為 async。未來若需進一步效能優化，可再考慮切換至 `asyncpg` 或 `psycopg3`（原生支援 async）。
