# 家教媒合與評價平台 系統規格書

**文件編號**：TMP-SPEC-2026-001
**版本**：v4.0
**建立日期**：2026 年 3 月 28 日
**最後更新**：2026 年 3 月 28 日

---

## 修訂紀錄

| 版本 | 日期 | 說明 |
|------|------|------|
| v1.0 | 2026-03-28 | 初版規劃，涵蓋基本功能範圍與資料庫設計 |
| v2.0 | 2026-03-28 | 新增訊息系統、媒合狀態機重構、三向評價、匯入匯出功能 |
| v3.0 | 2026-03-28 | 新增技術架構設計（huey worker、Repository Pattern、統一回應格式、一鍵啟動） |
| v4.0 | 2026-03-28 | 全文改寫為正式規格書格式，補充細部規格與邊界條件 |

---

## 目次

1. [專案總覽](#1-專案總覽)
2. [系統架構](#2-系統架構)
3. [技術架構詳細設計](#3-技術架構詳細設計)
4. [角色與權限模型](#4-角色與權限模型)
5. [功能模組規格](#5-功能模組規格)
6. [資料庫設計](#6-資料庫設計)
7. [API 端點規格](#7-api-端點規格)
8. [前端頁面與路由規格](#8-前端頁面與路由規格)
9. [非同步任務引擎規格](#9-非同步任務引擎規格)
10. [分工規劃](#10-分工規劃)
11. [開發排程](#11-開發排程)
12. [展示流程](#12-展示流程)
13. [附錄](#13-附錄)

---

## 1. 專案總覽

### 1.1 專案背景

本專案為 SQL（MS Access）通識課程之期末分組專題。課程要求使用 MS Access 作為資料庫管理系統，並於學期末進行上台報告與現場操作展示。

### 1.2 系統定位

本系統為一**雙邊媒合平台**，連結「家長（需求端）」與「家教老師（供給端）」兩方角色。系統核心功能涵蓋以下三大領域：

- **媒合機制**：家長依據科目、時薪、評分等條件搜尋老師，透過訊息溝通後發起媒合邀請，經雙方確認後成立教學合約。
- **教學管理**：老師於系統中記錄上課日誌與學生考試成績，家長可依權限查閱相關紀錄。
- **雙向評價**：合約結束後，家長可對老師、老師可對學生及家長分別進行多維度評價，評價結果構成平台信任機制。

### 1.3 設計目標

| 目標 | 說明 |
|------|------|
| 滿足課程要求 | 使用 MS Access 作為唯一資料庫，資料表設計與關聯圖可於 Access 內展示 |
| 展現軟體工程能力 | 採用三層式架構、RESTful API、JWT 認證、Repository Pattern、非同步任務引擎等業界標準實踐 |
| 不進行線上部署 | 全部服務運行於 localhost，展示時於本機操作 |

### 1.4 專案時程

預計開發期間為 5 週以上。最終交付形式為上台報告，搭配系統現場操作展示。

---

## 2. 系統架構

### 2.1 架構總覽

本系統採用三層式架構，分為前端展示層、後端 API 層、資料儲存層，另搭配獨立之非同步任務處理器（worker）。全部服務運行於 Windows 本機環境。

```
┌──────────────────────────────────────────────────────────────────────────┐
│                            Windows 本機環境                              │
│                                                                          │
│  ┌──────────────┐    HTTP/JSON     ┌──────────────┐    ODBC      ┌─────┐│
│  │  Vue 3 前端   │ ←─────────────→ │ FastAPI 後端  │ ←─────────→ │ MS  ││
│  │  (Vite)       │  localhost:5173  │  (uvicorn)    │   pyodbc   │Acce-││
│  │               │                  │               │            │ ss  ││
│  │  - Router     │                  │  - JWT 認證   │            │.acc-││
│  │  - Pinia      │                  │  - Pydantic   │            │ db  ││
│  │  - Axios      │                  │  - Repository │            │     ││
│  └──────────────┘                  │  - Logging    │            └─────┘│
│                                     └──────┬────────┘               ▲   │
│                                            │ 派發任務               │   │
│                                            ▼                       │   │
│                                     ┌──────────────┐    ODBC      │   │
│                                     │ huey worker   │ ────────────┘   │
│                                     │  (SQLite Q)   │                  │
│                                     │               │                  │
│                                     │  - CSV 匯入出 │                  │
│                                     │  - 報表計算   │                  │
│                                     │  - 定時任務   │                  │
│                                     │  - 假資料生成 │                  │
│                                     └──────────────┘                  │
│                                                                        │
│  啟動方式：start.bat 一鍵啟動三個 process                                │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Process 清單

系統運行時共啟動三個獨立 process，由 `start.bat` 統一管理。

| Process | 啟動指令 | 預設埠號 | 職責 |
|---------|---------|---------|------|
| FastAPI Server | `uvicorn app.main:app --reload --port 8000` | 8000 | 處理所有 HTTP 請求，提供 RESTful API |
| huey Worker | `python -m app.worker` | — | 執行背景任務（匯入匯出、報表計算、定時排程） |
| Vue Dev Server | `npm run dev` | 5173 | 提供前端單頁應用之開發伺服器 |

### 2.3 技術棧

| 層級 | 技術 | 版本 | 用途 |
|------|------|------|------|
| 前端框架 | Vue 3 + Vite | 3.x | 單頁應用（SPA） |
| 前端路由 | Vue Router | 4.x | 頁面路由與角色守衛 |
| 前端狀態管理 | Pinia | 2.x | 全域狀態（認證、快取） |
| HTTP 客戶端 | Axios | 1.x | API 呼叫，統一 interceptor |
| 後端框架 | FastAPI | 0.110+ | RESTful API，自動生成 Swagger 文件 |
| 資料驗證 | Pydantic | 2.x | Request/Response schema 定義 |
| 認證機制 | python-jose + passlib | — | JWT 簽發驗證、bcrypt 密碼雜湊 |
| 資料庫驅動 | pyodbc | 5.x | 透過 ODBC 連接 MS Access |
| 資料庫 | MS Access (.accdb) | 2016+ | 滿足課程要求之關聯式資料庫 |
| 任務佇列 | huey | 2.x | 輕量非同步任務引擎 |
| 任務 Broker | SQLite | — | huey 的訊息佇列儲存（零額外依賴） |
| 環境設定 | python-dotenv + pydantic-settings | — | .env 檔案管理組態 |
| 日誌 | Python logging (stdlib) | — | 結構化日誌，檔案輪轉 |
| 執行環境 | Windows 10/11 | — | pyodbc + Access ODBC Driver 僅支援 Windows |

---

## 3. 技術架構詳細設計

### 3.1 原始碼目錄結構

本專案採前後端分離架構，分置於兩個獨立之版本控制儲存庫（repository）。

#### 3.1.1 後端儲存庫：`tutor-platform-api`

```
tutor-platform-api/
├── .env                              # 環境變數（不納入版控）
├── .env.example                      # 環境變數範本（納入版控）
├── requirements.txt                  # Python 套件依賴清單
├── start.bat                         # 一鍵啟動腳本
├── README.md                         # 專案說明文件
│
├── app/
│   ├── __init__.py
│   ├── main.py                       # FastAPI 應用程式入口
│   ├── config.py                     # Pydantic Settings 組態類別
│   ├── database.py                   # pyodbc 連線管理
│   ├── dependencies.py               # FastAPI 依賴注入定義
│   ├── exceptions.py                 # 自定義例外與統一錯誤處理器
│   ├── worker.py                     # huey 實例初始化與任務註冊
│   │
│   ├── models/                       # Pydantic Schema 定義
│   │   ├── __init__.py
│   │   ├── common.py                 # ApiResponse、PaginatedResponse
│   │   ├── auth.py                   # LoginRequest、RegisterRequest、TokenResponse
│   │   ├── tutor.py                  # TutorCard、TutorDetail、TutorUpdate
│   │   ├── student.py                # StudentCreate、StudentUpdate
│   │   ├── match.py                  # MatchCreate、MatchStatusUpdate、ContractTerms
│   │   ├── session.py                # SessionCreate、SessionUpdate
│   │   ├── exam.py                   # ExamCreate、ExamUpdate
│   │   ├── review.py                 # ReviewCreate（三向共用）
│   │   ├── message.py                # MessageCreate
│   │   └── stats.py                  # IncomeStats、ExpenseStats、ProgressStats
│   │
│   ├── repositories/                 # 資料存取層（所有 SQL 語句僅存在於此層）
│   │   ├── __init__.py
│   │   ├── base.py                   # BaseRepository（通用 CRUD 輔助方法）
│   │   ├── auth_repo.py              # 使用者註冊、登入驗證、帳號查詢
│   │   ├── tutor_repo.py             # 老師搜尋、檔案管理、可用時段
│   │   ├── student_repo.py           # 學生資料 CRUD
│   │   ├── match_repo.py             # 媒合建立、狀態轉換、合約管理
│   │   ├── session_repo.py           # 上課日誌 CRUD、修改歷史記錄
│   │   ├── exam_repo.py              # 考試紀錄 CRUD
│   │   ├── review_repo.py            # 三向評價 CRUD、七日鎖定檢查
│   │   ├── message_repo.py           # 對話與訊息管理
│   │   └── stats_repo.py             # 統計彙總查詢
│   │
│   ├── routers/                      # API 路由層（不包含業務邏輯）
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── tutors.py
│   │   ├── students.py
│   │   ├── matches.py
│   │   ├── sessions.py
│   │   ├── exams.py
│   │   ├── reviews.py
│   │   ├── messages.py
│   │   ├── stats.py
│   │   └── admin.py                  # Super Admin 專用端點
│   │
│   ├── tasks/                        # huey 背景任務定義
│   │   ├── __init__.py
│   │   ├── import_export.py          # CSV 匯入匯出
│   │   ├── stats_tasks.py            # 報表預計算
│   │   ├── seed_tasks.py             # 假資料生成
│   │   └── scheduled.py              # 定時排程任務
│   │
│   └── utils/                        # 工具函式庫
│       ├── __init__.py
│       ├── security.py               # JWT 簽發驗證、密碼雜湊
│       ├── csv_handler.py            # CSV 讀寫與解析
│       └── logger.py                 # 日誌組態
│
├── logs/                             # 日誌輸出目錄
│   └── app.log
│
├── data/
│   ├── tutoring.accdb                # MS Access 資料庫檔案
│   └── huey.db                       # huey SQLite Broker 資料庫
│
└── seed/
    ├── generator.py                  # 假資料生成邏輯
    └── output/                       # 生成之 CSV 檔案暫存目錄
```

#### 3.1.2 前端儲存庫：`tutor-platform-web`

```
tutor-platform-web/
├── .env                              # 環境變數（API Base URL 等）
├── package.json
├── vite.config.js
├── README.md
│
├── public/
│
└── src/
    ├── main.js                       # Vue 應用程式入口
    ├── App.vue
    │
    ├── router/
    │   └── index.js                  # 路由定義與守衛邏輯
    │
    ├── stores/                       # Pinia 狀態管理模組
    │   ├── auth.js                   # 認證狀態、JWT Token、角色資訊
    │   ├── tutor.js                  # 老師搜尋與檔案快取
    │   ├── match.js                  # 配對狀態管理
    │   └── message.js                # 訊息狀態管理
    │
    ├── api/                          # Axios API 封裝層
    │   ├── index.js                  # Axios 實例建立與 Interceptor 設定
    │   ├── auth.js
    │   ├── tutors.js
    │   ├── matches.js
    │   ├── sessions.js
    │   ├── exams.js
    │   ├── reviews.js
    │   ├── messages.js
    │   ├── stats.js
    │   └── admin.js
    │
    ├── views/                        # 頁面級元件
    │   ├── LoginView.vue
    │   ├── RegisterView.vue
    │   ├── parent/
    │   │   ├── DashboardView.vue
    │   │   ├── SearchView.vue
    │   │   ├── TutorDetailView.vue
    │   │   ├── StudentsView.vue
    │   │   ├── MatchDetailView.vue
    │   │   └── ExpenseView.vue
    │   ├── tutor/
    │   │   ├── DashboardView.vue
    │   │   ├── ProfileView.vue
    │   │   ├── MatchDetailView.vue
    │   │   └── IncomeView.vue
    │   ├── messages/
    │   │   ├── ConversationListView.vue
    │   │   └── ChatView.vue
    │   └── admin/
    │       └── AdminDashboardView.vue
    │
    └── components/                   # 可重用元件
        ├── common/
        │   ├── AppHeader.vue
        │   ├── AppSidebar.vue
        │   └── LoadingSpinner.vue
        ├── tutor/
        │   ├── TutorCard.vue
        │   ├── TutorFilter.vue
        │   └── AvailabilityCalendar.vue
        ├── match/
        │   ├── MatchStatusBadge.vue
        │   ├── ContractForm.vue
        │   └── InviteForm.vue
        ├── review/
        │   ├── ReviewForm.vue        # 三向共用元件
        │   ├── ReviewList.vue
        │   └── RadarChart.vue
        ├── session/
        │   ├── SessionForm.vue
        │   └── SessionTimeline.vue
        └── stats/
            ├── IncomeChart.vue
            ├── ExpenseChart.vue
            └── ProgressChart.vue
```

### 3.2 統一 API 回應格式

所有 API 端點之回應均採用統一之 `ApiResponse` 結構封裝。此設計使前端 Axios Interceptor 得以統一處理成功與失敗情境，無需逐端點判斷回應格式。

#### 3.2.1 回應結構定義

```python
# app/models/common.py
from pydantic import BaseModel
from typing import TypeVar, Generic, Optional, List

T = TypeVar("T")

class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: Optional[T] = None
    message: Optional[str] = None

class PaginatedData(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
```

#### 3.2.2 回應範例

**一般成功回應**
```json
{
  "success": true,
  "data": { "user_id": 1, "role": "tutor", "display_name": "王小明" },
  "message": null
}
```

**分頁查詢回應**
```json
{
  "success": true,
  "data": {
    "items": [ ... ],
    "total": 87,
    "page": 1,
    "page_size": 20
  },
  "message": null
}
```

**錯誤回應**
```json
{
  "success": false,
  "data": null,
  "message": "該老師目前不接受新學生"
}
```

#### 3.2.3 統一錯誤處理

```python
# app/exceptions.py
from fastapi import Request
from fastapi.responses import JSONResponse

class AppException(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code

class NotFoundException(AppException):
    def __init__(self, message: str = "資源不存在"):
        super().__init__(message, 404)

class ForbiddenException(AppException):
    def __init__(self, message: str = "無權限執行此操作"):
        super().__init__(message, 403)

class ConflictException(AppException):
    def __init__(self, message: str = "資源狀態衝突"):
        super().__init__(message, 409)

async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "data": None, "message": exc.message}
    )
```

### 3.3 Repository Pattern

本系統採用 Repository Pattern 作為資料存取抽象層。所有 SQL 語句僅存在於 `repositories/` 目錄下之各 Repository 類別中，Router 層透過呼叫 Repository 方法存取資料，不得直接撰寫 SQL。

此設計之目的如下：
- 將資料存取邏輯集中管理，便於維護與除錯。
- Router 層僅負責請求驗證與回應封裝，職責單一。
- 未來若需替換資料庫引擎（如由 Access 遷移至 PostgreSQL），僅需修改 Repository 層。

#### 3.3.1 BaseRepository

```python
# app/repositories/base.py
class BaseRepository:
    """所有 Repository 之基礎類別，提供通用之資料存取方法。"""

    def __init__(self, conn):
        self.conn = conn
        self.cursor = conn.cursor()

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        """執行查詢並回傳單筆結果（dict 格式），查無資料時回傳 None。"""
        self.cursor.execute(sql, params)
        row = self.cursor.fetchone()
        if row is None:
            return None
        columns = [desc[0] for desc in self.cursor.description]
        return dict(zip(columns, row))

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        """執行查詢並回傳全部結果（list of dict 格式）。"""
        self.cursor.execute(sql, params)
        rows = self.cursor.fetchall()
        columns = [desc[0] for desc in self.cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def execute(self, sql: str, params: tuple = ()) -> None:
        """執行寫入操作（INSERT / UPDATE / DELETE）並提交交易。"""
        self.cursor.execute(sql, params)
        self.conn.commit()

    def execute_returning_id(self, sql: str, params: tuple = ()) -> int:
        """執行 INSERT 並回傳自動產生之主鍵值（AutoNumber）。"""
        self.cursor.execute(sql, params)
        self.cursor.execute("SELECT @@IDENTITY")
        new_id = self.cursor.fetchone()[0]
        self.conn.commit()
        return new_id

    def fetch_paginated(self, sql: str, params: tuple, page: int, page_size: int) -> tuple[list[dict], int]:
        """
        執行分頁查詢。
        由於 MS Access 不支援 LIMIT/OFFSET 語法，故先取回全部結果，
        再於 Python 端進行分頁切割。
        回傳值：(items, total_count)
        """
        all_rows = self.fetch_all(sql, params)
        total = len(all_rows)
        start = (page - 1) * page_size
        items = all_rows[start:start + page_size]
        return items, total
```

#### 3.3.2 Repository 使用範例

```python
# app/repositories/tutor_repo.py
from .base import BaseRepository

class TutorRepository(BaseRepository):
    """老師相關之資料存取操作。"""

    def search(
        self,
        subject_id: int | None = None,
        min_rate: float | None = None,
        max_rate: float | None = None,
        min_rating: float | None = None,
        school: str | None = None
    ) -> list[dict]:
        """
        依據篩選條件搜尋老師。
        所有篩選條件皆為可選，未提供之條件不納入查詢。
        """
        sql = """
            SELECT t.tutor_id, u.display_name, t.university, t.department,
                   t.grade_year, t.max_students, t.show_university,
                   t.show_department, t.show_grade_year,
                   t.show_hourly_rate, t.show_subjects
            FROM Tutors t
            INNER JOIN Users u ON t.user_id = u.user_id
            WHERE 1=1
        """
        params = []

        if subject_id is not None:
            sql += " AND t.tutor_id IN (SELECT tutor_id FROM Tutor_Subjects WHERE subject_id = ?)"
            params.append(subject_id)
        if min_rate is not None:
            sql += " AND t.tutor_id IN (SELECT tutor_id FROM Tutor_Subjects WHERE hourly_rate >= ?)"
            params.append(min_rate)
        if max_rate is not None:
            sql += " AND t.tutor_id IN (SELECT tutor_id FROM Tutor_Subjects WHERE hourly_rate <= ?)"
            params.append(max_rate)
        if school is not None:
            sql += " AND t.university LIKE ?"
            params.append(f"%{school}%")

        return self.fetch_all(sql, tuple(params))

    def get_avg_rating(self, tutor_id: int) -> dict | None:
        """取得指定老師之各維度平均評分與評價總數。"""
        sql = """
            SELECT AVG(rating_1) AS avg_teaching,
                   AVG(rating_2) AS avg_punctuality,
                   AVG(rating_3) AS avg_progress,
                   AVG(rating_4) AS avg_communication,
                   COUNT(*)      AS review_count
            FROM Reviews
            WHERE match_id IN (SELECT match_id FROM Matches WHERE tutor_id = ?)
              AND review_type = 'parent_to_tutor'
        """
        return self.fetch_one(sql, (tutor_id,))

    def get_active_student_count(self, tutor_id: int) -> int:
        """取得指定老師目前進行中之學生數（status 為 active 或 trial）。"""
        sql = """
            SELECT COUNT(*) AS cnt
            FROM Matches
            WHERE tutor_id = ? AND status IN ('active', 'trial')
        """
        result = self.fetch_one(sql, (tutor_id,))
        return result["cnt"] if result else 0
```

#### 3.3.3 Router 層呼叫規範

Router 層之職責限定為：接收請求、驗證參數、呼叫 Repository、封裝回應。不得包含 SQL 語句或複雜業務邏輯。

```python
# app/routers/tutors.py
from fastapi import APIRouter, Depends, Query
from app.dependencies import get_db, get_current_user
from app.repositories.tutor_repo import TutorRepository
from app.models.common import ApiResponse

router = APIRouter(prefix="/api/tutors", tags=["tutors"])

@router.get("", response_model=ApiResponse)
async def search_tutors(
    subject_id: int = Query(None),
    min_rate: float = Query(None),
    max_rate: float = Query(None),
    min_rating: float = Query(None),
    school: str = Query(None),
    sort_by: str = Query("rating"),
    conn=Depends(get_db)
):
    repo = TutorRepository(conn)
    tutors = repo.search(subject_id, min_rate, max_rate, min_rating, school)

    for t in tutors:
        rating_info = repo.get_avg_rating(t["tutor_id"])
        t["avg_rating"] = rating_info
        # 依據 show_xxx 欄位過濾不公開之資訊
        if not t.pop("show_university"):
            t.pop("university", None)
        if not t.pop("show_department"):
            t.pop("department", None)
        # ... 其餘 show_xxx 欄位同理

    return ApiResponse(success=True, data=tutors)
```

### 3.4 資料庫連線管理

```python
# app/database.py
import pyodbc
from app.config import Settings

settings = Settings()

def get_connection() -> pyodbc.Connection:
    """建立並回傳一個新的 MS Access ODBC 連線。"""
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        rf"DBQ={settings.access_db_path};"
    )
    return pyodbc.connect(conn_str)

def get_db():
    """FastAPI 依賴注入用之 generator。每次請求建立連線，請求結束時關閉。"""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
```

### 3.5 環境變數管理

系統組態透過 `.env` 檔案管理，並以 `pydantic-settings` 進行型別安全之讀取與驗證。

```python
# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # 資料庫
    access_db_path: str = "data/tutoring.accdb"

    # JWT 認證
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Super Admin 帳號（系統啟動時自動建立）
    admin_username: str = "admin"
    admin_password: str = "admin123"

    # huey 任務佇列
    huey_db_path: str = "data/huey.db"

    # 日誌
    log_file: str = "logs/app.log"
    log_level: str = "INFO"

    # CORS
    cors_origins: str = "http://localhost:5173"

    class Config:
        env_file = ".env"
```

```ini
# .env.example
ACCESS_DB_PATH=data/tutoring.accdb
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-me
HUEY_DB_PATH=data/huey.db
LOG_FILE=logs/app.log
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:5173
```

### 3.6 統一日誌機制

系統採用 Python 標準函式庫之 `logging` 模組，搭配 `RotatingFileHandler` 實現日誌檔案輪轉。所有日誌同時輸出至 console 與檔案。

```python
# app/utils/logger.py
import logging
from logging.handlers import RotatingFileHandler
from app.config import Settings

def setup_logger() -> logging.Logger:
    settings = Settings()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        settings.log_file,
        maxBytes=10 * 1024 * 1024,   # 每檔上限 10 MB
        backupCount=5,                # 保留最近 5 個輪轉檔案
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger("app")
    root_logger.setLevel(getattr(logging, settings.log_level))
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    return root_logger
```

**日誌輸出格式範例**：
```
2026-04-15 14:23:01 | INFO     | app.routers.auth          | 使用者 john_parent 登入成功
2026-04-15 14:23:05 | WARNING  | app.repositories.match    | 配對 #42 狀態轉換被拒絕：trial → paused 不合法
2026-04-15 14:24:00 | INFO     | app.tasks.import_export   | CSV 匯入完成：Users 表，共 25 筆，模式 upsert
2026-04-15 14:25:30 | ERROR    | app.repositories.base     | SQL 執行失敗：INSERT INTO Sessions ... [詳細錯誤]
```

### 3.7 一鍵啟動腳本

```bat
@REM start.bat — 一鍵啟動系統全部服務
@echo off
chcp 65001 >nul
echo ================================================
echo   家教媒合與評價平台 — 系統啟動程序
echo ================================================
echo.

REM 環境檢查
if not exist ".env" (
    echo [錯誤] 未偵測到 .env 檔案。
    echo         請複製 .env.example 為 .env 並修改相關設定。
    pause
    exit /b 1
)

if not exist "data\tutoring.accdb" (
    echo [警告] 未偵測到 Access 資料庫檔案，將執行初始化程序...
    python -m app.database --init
    if errorlevel 1 (
        echo [錯誤] 資料庫初始化失敗。
        pause
        exit /b 1
    )
)

REM 啟動 huey worker
echo [1/3] 啟動 huey worker（背景任務處理器）...
start "huey-worker" cmd /k "python -m app.worker"

REM 啟動 FastAPI
echo [2/3] 啟動 FastAPI Server...
start "fastapi-server" cmd /k "uvicorn app.main:app --reload --port 8000"

REM 等待 API Server 就緒
timeout /t 3 /nobreak >nul

REM 啟動前端開發伺服器
echo [3/3] 啟動 Vue Dev Server...
cd /d "../tutor-platform-web"
start "vue-dev-server" cmd /k "npm run dev"

echo.
echo ================================================
echo   全部服務啟動完成
echo.
echo   API Server:   http://localhost:8000
echo   Swagger UI:   http://localhost:8000/docs
echo   前端介面:     http://localhost:5173
echo ================================================
pause
```

### 3.8 前端 Axios 統一封裝

```javascript
// src/api/index.js
import axios from 'axios'
import { useAuthStore } from '@/stores/auth'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 30000,
})

// Request Interceptor：自動附加 JWT Token
api.interceptors.request.use(config => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

// Response Interceptor：統一解包回應
api.interceptors.response.use(
  response => {
    const { success, data, message } = response.data
    if (!success) {
      // 通知 UI 顯示錯誤訊息（依所選元件庫實作）
      return Promise.reject(new Error(message))
    }
    return data  // 成功時直接回傳 data 層，呼叫端無需逐層解包
  },
  error => {
    if (error.response?.status === 401) {
      const auth = useAuthStore()
      auth.logout()
      window.location.href = '/login'
    }
    const message = error.response?.data?.message || '網路連線異常'
    return Promise.reject(new Error(message))
  }
)

export default api
```

---

## 4. 角色與權限模型

### 4.1 角色定義

本系統定義三種使用者角色，各角色之帳號建立方式與權限範圍如下表所述。

| 角色 | 識別碼 | 帳號建立方式 | 說明 |
|------|--------|-------------|------|
| Super Admin | `admin` | `.env` 檔案指定帳號密碼，系統啟動時自動寫入 Users 表 | 系統管理者，負責資料匯入匯出、假資料生成、系統狀態監控 |
| 家長 | `parent` | 使用者自行於註冊頁面建立 | 需求端，搜尋老師、管理子女資料、發起媒合、撰寫評價 |
| 家教老師 | `tutor` | 使用者自行於註冊頁面建立 | 供給端，管理個人檔案、接受媒合、記錄教學日誌與考試成績 |

### 4.2 權限矩陣

| 功能 | Super Admin | 家長 | 老師 |
|------|:-----------:|:----:|:----:|
| 系統管理後台 | ✓ | ✗ | ✗ |
| 一鍵匯入匯出 | ✓ | ✗ | ✗ |
| 假資料生成 | ✓ | ✗ | ✗ |
| 清空資料庫 | ✓ | ✗ | ✗ |
| 查看所有使用者帳號 | ✓ | ✗ | ✗ |
| 搜尋老師 | ✓ | ✓ | ✗ |
| 管理子女資料 | ✗ | ✓ | ✗ |
| 發起媒合邀請 | ✗ | ✓ | ✗ |
| 接受/拒絕媒合 | ✗ | ✗ | ✓ |
| 記錄上課日誌 | ✗ | ✗ | ✓ |
| 查看上課日誌 | ✗ | 依 visible_to_parent | ✓（自己的） |
| 新增考試紀錄 | ✗ | ✓ | ✓ |
| 查看考試紀錄 | ✗ | 依 visible_to_parent | ✓（自己的） |
| 撰寫評價 | ✗ | ✓（評老師） | ✓（評學生、評家長） |
| 傳送訊息 | ✓ | ✓ | ✓ |
| 查看收入統計 | ✗ | ✗ | ✓（自己的） |
| 查看支出統計 | ✗ | ✓（自己的） | ✗ |
| 編輯老師檔案 | ✗ | ✗ | ✓（自己的） |

### 4.3 前端路由守衛規則

| 使用者狀態 | 嘗試訪問路徑 | 系統行為 |
|-----------|-------------|---------|
| 未登入 | 任何受保護頁面 | 重導至 `/login` |
| role = parent | `/tutor/*` 或 `/admin/*` | 重導至 `/parent/dashboard` |
| role = tutor | `/parent/*` 或 `/admin/*` | 重導至 `/tutor/dashboard` |
| role = admin | 任何路徑 | 允許存取 |

---

## 5. 功能模組規格

### 5.1 模組 A：身份驗證

#### 5.1.1 註冊

- 使用者選擇角色（家長或老師），填寫帳號、密碼、姓名、電話、電子信箱。
- 密碼以 bcrypt 演算法雜湊後儲存。
- 若角色為老師，註冊完成後自動建立一筆空白之 Tutors 延伸資料。

#### 5.1.2 登入

- 驗證帳號密碼後簽發 JWT Token，Token 中包含 `user_id`、`role`、過期時間。
- Token 有效期限預設為 60 分鐘，可於 `.env` 中調整。
- 前端將 Token 存入 localStorage，每次 API 請求自動附加於 `Authorization` 標頭。

#### 5.1.3 Super Admin 初始化

系統啟動時（`main.py` 之 `startup` 事件），檢查 Users 表中是否已存在 `.env` 中指定之管理員帳號。若不存在，則自動插入一筆 `role = admin` 之使用者紀錄。

### 5.2 模組 B：訊息系統

#### 5.2.1 設計原則

- 一對一對話模式，每兩位使用者之間最多存在一個 Conversation。
- 僅支援純文字訊息，不支援檔案傳送、已讀標記或即時推播。
- 任何使用者均可主動向任何其他使用者發起對話。

#### 5.2.2 功能規格

| 功能 | 說明 |
|------|------|
| 對話列表 | 依最後訊息時間降冪排列，顯示對方姓名與最新訊息摘要 |
| 對話頁面 | 依時間序列顯示雙方訊息，底部設有文字輸入區與送出按鈕 |
| 開啟新對話 | 由老師詳情頁之「傳送訊息」按鈕觸發；API 先查詢雙方是否已有既存對話，有則回傳既有 conversation_id，無則新建 |

### 5.3 模組 C：搜尋與老師檔案

#### 5.3.1 搜尋頁面

**篩選條件**

| 條件 | 輸入方式 | 說明 |
|------|---------|------|
| 科目 | 下拉選單或多選標籤 | 篩選可教授指定科目之老師 |
| 時薪範圍 | 數值輸入（最低～最高） | 篩選時薪落於指定區間之老師 |
| 評分門檻 | 數值輸入 | 僅顯示平均評分大於等於指定值之老師 |
| 學校/科系 | 文字輸入 | 模糊比對 |

**排序方式**

使用者可自行選擇排序依據，系統提供以下選項：評分最高優先、時薪最低優先、最新註冊優先。

**老師卡片顯示規則**

系統強制顯示（不可隱藏）之欄位：姓名、平均評分、評價數量。

老師可透過個人檔案設定之 `show_xxx` 欄位，控制以下資訊是否對外顯示：學校、科系、年級、時薪範圍、可教科目。

#### 5.3.2 老師詳情頁

於搜尋結果卡片資訊之基礎上，額外顯示以下內容：

| 區塊 | 內容 |
|------|------|
| 自我介紹 | 完整自介文字與教學經歷 |
| 評價 | 各維度平均分之雷達圖、歷史評價列表 |
| 接案狀態 | 已接 N 位學生 / 上限 M 位（源自 `max_students` 設定） |
| 可用時段 | 行事曆形式呈現每週可用時段（源自 `Tutor_Availability` 表） |
| 操作按鈕 | 「傳送訊息」（開啟對話）、「送出邀請」（進入媒合流程） |

#### 5.3.3 老師個人檔案編輯

老師可編輯之欄位清單：

| 類別 | 欄位 |
|------|------|
| 基本資料 | 姓名、學校、科系、年級、自我介紹、教學經歷 |
| 教學設定 | 可教科目（多選，各科可設定不同時薪）、最大接案學生數 |
| 時段設定 | 每週可用時段（星期幾、起訖時間） |
| 隱私設定 | 各欄位對外公開與否（show_university、show_department 等） |

### 5.4 模組 D：媒合流程與合約

#### 5.4.1 狀態機定義

Matches 表之 `status` 欄位管理配對生命週期，共定義 8 種狀態。

```
                    ┌──────────────────────────────────────────────────────┐
                    │                                                      │
  [家長送出邀請]     │    [家長撤回]                                         │
       │            │         │                                            │
       ▼            │         ▼                                            │
   ┌────────┐       │    ┌──────────┐                                     │
   │pending │───────┘──→ │cancelled │                                     │
   └────────┘             └──────────┘                                    │
       │                                                                   │
       │ [老師接受]                                                         │
       │                                                                   │
       │ ┌─ want_trial=Yes ─→ ┌───────┐ [雙方確認] → ┌────────┐          │
       │ │                     │ trial │─────────────→│ active │          │
       │ │                     └───────┘              └────────┘          │
       │ │                          │                      │  ▲           │
       │ │                   [任一方不滿意]          [暫停]  │  │[恢復]    │
       │ │                          │                      ▼  │           │
       │ │                          ▼                 ┌────────┐          │
       │ │                     ┌──────────┐           │ paused │          │
       │ │                     │ rejected │           └────────┘          │
       │ │                     └──────────┘                │              │
       │ │                                          [提出終止]             │
       │ └─ want_trial=No ──→ 直接進入 active              │              │
       │                                                   ▼              │
       │ [老師拒絕]                                 ┌──────────────┐      │
       └──────────→ rejected                        │ terminating  │      │
                                                    │ (等對方同意)  │      │
                                                    └──────────────┘      │
                                                           │               │
                                                    [對方同意]              │
                                                           │    [對方不同意]│
                                                           ▼       ────────┘
                                                     ┌────────┐
                                                     │ ended  │
                                                     └────────┘
                                                           │
                                                    [開放評價，7 日內可修改]
```

#### 5.4.2 狀態轉換規則

| 當前狀態 | 觸發動作 | 操作者 | 目標狀態 | 備註 |
|---------|---------|--------|---------|------|
| pending | 撤回邀請 | 家長 | cancelled | — |
| pending | 拒絕邀請 | 老師 | rejected | — |
| pending | 接受邀請 | 老師 | trial 或 active | 依 `want_trial` 欄位決定 |
| trial | 雙方確認 | 家長＋老師 | active | 需雙方均確認方可轉換 |
| trial | 不滿意 | 家長或老師 | rejected | 任一方即可觸發 |
| active | 暫停 | 家長或老師 | paused | — |
| active | 提出終止 | 家長或老師 | terminating | 記錄 `terminated_by` |
| paused | 恢復 | 家長或老師 | active | — |
| paused | 提出終止 | 家長或老師 | terminating | — |
| terminating | 同意終止 | 對方 | ended | — |
| terminating | 不同意 | 對方 | active 或 paused | 回到提出終止前之狀態 |

#### 5.4.3 合約條款欄位

以下欄位儲存於 Matches 表中，於雙方簽約階段填入。

| 欄位 | 型態 | 說明 |
|------|------|------|
| hourly_rate | Currency | 正式授課時薪 |
| sessions_per_week | Integer | 約定之每週堂數 |
| start_date | Date | 合約起始日期 |
| end_date | Date | 合約結束日期（可為空值，於終止時填入） |
| penalty_amount | Currency | 提前終止之違約金金額 |
| trial_price | Currency | 試教單次費用（通常低於正式時薪） |
| trial_count | Integer | 約定之試教次數 |
| contract_notes | Memo | 其他附加條款（自由文字） |

#### 5.4.4 邀請附帶資訊

家長送出媒合邀請時，須填寫以下資訊：

| 欄位 | 必填 | 說明 |
|------|:----:|------|
| 指定子女 | ✓ | 從家長已建立之子女清單中選取 |
| 科目 | ✓ | 從老師可教授之科目中選取 |
| 提議時薪 | ✓ | 家長提議之時薪金額 |
| 提議每週堂數 | ✓ | 家長希望之每週上課次數 |
| 是否試教 | ✓ | 布林值，勾選後配對將先進入 trial 階段 |
| 留言 | 選填 | 文字留言，說明教學需求或期望 |

### 5.5 模組 E：上課日誌

#### 5.5.1 日誌欄位

| 欄位 | 必填 | 說明 |
|------|:----:|------|
| 上課日期 | ✓ | 日期選擇 |
| 上課時數 | ✓ | 數值輸入（支援小數，如 1.5 小時） |
| 內容摘要 | ✓ | 本次上課之教學內容紀錄 |
| 指派作業 | 選填 | 本次課後指派之作業內容 |
| 學生當堂表現 | 選填 | 教師對學生該堂表現之觀察紀錄 |
| 下次預計進度 | 選填 | 下次上課之預計教學範圍 |
| 是否公開予家長 | ✓ | 布林值，預設為否 |

#### 5.5.2 權限規則

- 僅配對之老師可新增與編輯上課日誌。
- 家長僅能檢視 `visible_to_parent = Yes` 之日誌紀錄。
- 家長 Dashboard 首頁顯示所有子女最近之已公開日誌。

#### 5.5.3 修改歷史機制

日誌送出後允許修改，惟每次修改均於 `Session_Edit_Logs` 表留下紀錄，記錄內容包含：被修改之欄位名稱、修改前內容、修改後內容、修改時間。

### 5.6 模組 F：考試紀錄

#### 5.6.1 紀錄欄位

| 欄位 | 必填 | 說明 |
|------|:----:|------|
| 考試日期 | ✓ | 日期選擇 |
| 科目 | ✓ | 從系統科目清單中選取 |
| 考試類型 | ✓ | 下拉選單：段考、模考、隨堂考 |
| 分數 | ✓ | 數值輸入 |
| 是否公開予家長 | ✓ | 布林值 |

本版本不包含試題相關內容（如題目、錯題詳解等）。

#### 5.6.2 權限規則

- 老師與家長均可新增考試紀錄，系統記錄新增者之 `user_id`。
- 老師新增之紀錄，依 `visible_to_parent` 決定家長是否可見。
- 家長自行新增之紀錄，`visible_to_parent` 強制為 Yes。

#### 5.6.3 進步幅度計算

進步幅度不儲存於資料庫，而是由前端取得同一學生同一科目之歷次考試分數後，計算相鄰兩次考試之分數差值進行顯示。

### 5.7 模組 G：三向評價系統

#### 5.7.1 設計原則

三種評價方向共用 `Reviews` 表，以 `review_type` 欄位區分方向。評分欄位使用通用命名（`rating_1` 至 `rating_4`），前端依據 `review_type` 之值顯示對應之維度標籤。此設計使評價相關之前端元件（`ReviewForm.vue`、`ReviewList.vue`）得以跨方向重複使用。

#### 5.7.2 各方向之維度定義

**家長 → 老師（`review_type = 'parent_to_tutor'`）**

| 通用欄位 | 維度標籤 | 分數範圍 |
|---------|---------|---------|
| rating_1 | 教學品質 | 1–5 |
| rating_2 | 準時度 | 1–5 |
| rating_3 | 學生進步程度 | 1–5 |
| rating_4 | 溝通態度 | 1–5 |
| personality_comment | 性格評價 | 自由文字 |
| comment | 整體評論 | 自由文字 |

**老師 → 學生（`review_type = 'tutor_to_student'`）**

| 通用欄位 | 維度標籤 | 分數範圍 |
|---------|---------|---------|
| rating_1 | 學習態度 | 1–5 |
| rating_2 | 作業完成度 | 1–5 |
| rating_3 | 預留 | 可為空值 |
| rating_4 | 預留 | 可為空值 |
| personality_comment | 性格評價 | 自由文字 |
| comment | 整體評論 | 自由文字 |

**老師 → 家長（`review_type = 'tutor_to_parent'`）**

| 通用欄位 | 維度標籤 | 分數範圍 |
|---------|---------|---------|
| rating_1 | 配合度（準時、不臨時取消） | 1–5 |
| rating_2 | 溝通態度（聯絡便利性、尊重程度） | 1–5 |
| rating_3 | 繳費準時度 | 1–5 |
| rating_4 | 預留 | 可為空值 |
| personality_comment | 性格評價 | 自由文字 |
| comment | 整體評論 | 自由文字 |

#### 5.7.3 評價規則

| 規則 | 說明 |
|------|------|
| 觸發時機 | 配對狀態變為 `ended` 後方可撰寫評價 |
| 次數限制 | 每段配對之每個方向僅限撰寫一次 |
| 修改期限 | 評價送出後 7 日內允許修改，逾期後鎖定 |
| 鎖定機制 | API 端計算 `created_at` 與目前時間之差值，超過 7 日則回傳 HTTP 403 |
| 定時清理 | huey 排程任務於每日凌晨 3:00 執行，可進行過期評價之標記或其他清理作業 |

#### 5.7.4 評價聚合顯示

- 老師詳情頁：以雷達圖呈現四個維度之平均分數，並以列表形式展示歷史評價。
- 配對詳情頁：展示該配對之所有方向評價。

### 5.8 模組 H：Dashboard

#### 5.8.1 老師 Dashboard

| 區塊 | 顯示內容 |
|------|---------|
| 摘要卡片 | 目前學生數 / 接案上限、本月收入金額、待處理邀請數量 |
| 待處理 | `status = pending` 之邀請列表 |
| 進行中 | `status IN (active, trial, paused)` 之配對列表，點擊可進入配對詳情 |

#### 5.8.2 家長 Dashboard

| 區塊 | 顯示內容 |
|------|---------|
| 子女列表 | 各子女姓名及其目前配對狀態一覽 |
| 待回覆邀請 | `status = pending` 之已送出邀請 |
| 最近動態 | 跨子女之最新已公開上課日誌 |
| 最新成績 | 各子女之最新已公開考試成績 |

### 5.9 模組 I：統計報表

#### 5.9.1 老師收入統計

- 支援三種分群維度：按月份、按學生、按科目。
- 計算公式：`SUM(Sessions.hours × Matches.hourly_rate)`，依所選維度進行 `GROUP BY`。
- 前端呈現：柱狀圖搭配數據表格。
- 計算方式：透過 huey 背景任務執行，避免阻塞 API 回應。

#### 5.9.2 家長支出統計

- 與老師收入統計對稱，支援按月份、按子女、按科目分群。
- 計算公式同上。

#### 5.9.3 學生成績趨勢

- 折線圖：X 軸為考試日期，Y 軸為分數，支援按科目篩選。
- 表格：歷次考試清單，各筆顯示與同科目上次考試之分數差值（前端計算）。

### 5.10 模組 J：匯入匯出與假資料

#### 5.10.1 支援格式

CSV（逗號分隔值）。

#### 5.10.2 匯出

- 全部 13 張資料表均支援匯出。
- 匯出操作透過 huey 背景任務執行，API 立即回傳 `task_id`，前端以 polling 方式查詢任務狀態，完成後提供檔案下載。

#### 5.10.3 匯入

- 預設模式：比對式更新（upsert）——依主鍵比對，存在則更新，不存在則新增。
- Super Admin 專用模式：完全覆蓋（overwrite）——清空目標表後全量寫入。
- 匯入操作同樣透過 huey 背景任務執行，避免大量資料阻塞 API。

#### 5.10.4 假資料生成器

- 以 huey 背景任務形式運行，由 Admin 後台之按鈕觸發。
- 生成邏輯包含：中文姓名、台灣大專院校名稱、科目組合、合理之評價文字與分數分布等。
- 生成流程：產出各表之 CSV 字串 → 呼叫匯入任務逐表寫入 Access → 回傳生成結果。

### 5.11 模組 K：Super Admin 後台

| 功能 | 說明 |
|------|------|
| 一鍵匯入/匯出 | 可選擇單表或全部資料表，操作透過 huey 背景任務執行 |
| 清空資料庫 | 確認對話框 → 刪除所有資料表之內容（保留 Admin 帳號與表結構） |
| 使用者管理 | 顯示所有帳號之列表（支援搜尋） |
| 系統狀態 | 顯示統計數據：總帳號數、老師數、家長數、配對數、本月活躍配對數等 |
| 假資料生成 | 按鈕觸發 → 背景生成並匯入 → 介面顯示進度 |

---

## 6. 資料庫設計

### 6.1 資料表總覽

本系統共設計 13 張資料表，以下依功能分群列示。

**身份與角色**：Users、Tutors、Students
**科目與時段**：Subjects、Tutor_Subjects、Tutor_Availability
**溝通**：Conversations、Messages
**媒合與合約**：Matches
**教學紀錄**：Sessions、Session_Edit_Logs、Exams
**評價**：Reviews

### 6.2 各表欄位規格

#### 6.2.1 Users（使用者帳號）

| 欄位 | 資料型態 | 限制 | 說明 |
|------|---------|------|------|
| user_id | AutoNumber | PK | 主鍵 |
| username | Text(50) | UNIQUE, NOT NULL | 登入帳號 |
| password_hash | Text(255) | NOT NULL | bcrypt 雜湊密碼 |
| role | Text(10) | NOT NULL | `tutor` / `parent` / `admin` |
| display_name | Text(50) | NOT NULL | 顯示名稱 |
| phone | Text(20) | | 聯絡電話 |
| email | Text(100) | | 電子信箱 |
| created_at | DateTime | NOT NULL | 帳號建立時間 |

#### 6.2.2 Tutors（老師延伸資料）

| 欄位 | 資料型態 | 限制 | 說明 |
|------|---------|------|------|
| tutor_id | AutoNumber | PK | 主鍵 |
| user_id | Long Integer | FK → Users, UNIQUE | 對應帳號 |
| university | Text(50) | | 就讀大學 |
| department | Text(50) | | 科系 |
| grade_year | Integer | | 年級 |
| self_intro | Memo | | 自我介紹 |
| teaching_experience | Memo | | 教學經歷 |
| max_students | Integer | DEFAULT 5 | 最大接案學生數 |
| show_university | Yes/No | DEFAULT Yes | 是否公開學校 |
| show_department | Yes/No | DEFAULT Yes | 是否公開科系 |
| show_grade_year | Yes/No | DEFAULT Yes | 是否公開年級 |
| show_hourly_rate | Yes/No | DEFAULT Yes | 是否公開時薪 |
| show_subjects | Yes/No | DEFAULT Yes | 是否公開可教科目 |

#### 6.2.3 Students（學生）

| 欄位 | 資料型態 | 限制 | 說明 |
|------|---------|------|------|
| student_id | AutoNumber | PK | 主鍵 |
| parent_user_id | Long Integer | FK → Users, NOT NULL | 所屬家長帳號 |
| name | Text(50) | NOT NULL | 學生姓名 |
| school | Text(50) | | 目前就讀學校 |
| grade | Text(20) | | 年級 |
| target_school | Text(50) | | 目標學校 |
| parent_phone | Text(20) | | 家長電話 |
| notes | Memo | | 備註 |

#### 6.2.4 Subjects（科目）

| 欄位 | 資料型態 | 限制 | 說明 |
|------|---------|------|------|
| subject_id | AutoNumber | PK | 主鍵 |
| subject_name | Text(30) | NOT NULL, UNIQUE | 科目名稱 |
| category | Text(20) | NOT NULL | 分類：`math` / `science` / `lang` / `other` |

#### 6.2.5 Tutor_Subjects（老師可教科目）

| 欄位 | 資料型態 | 限制 | 說明 |
|------|---------|------|------|
| tutor_id | Long Integer | FK → Tutors, 聯合 PK | 老師 |
| subject_id | Long Integer | FK → Subjects, 聯合 PK | 科目 |
| hourly_rate | Currency | NOT NULL | 該科目之時薪 |

#### 6.2.6 Tutor_Availability（老師可用時段）

| 欄位 | 資料型態 | 限制 | 說明 |
|------|---------|------|------|
| availability_id | AutoNumber | PK | 主鍵 |
| tutor_id | Long Integer | FK → Tutors, NOT NULL | 老師 |
| day_of_week | Integer | NOT NULL, 1–7 | 星期（1=週一 ~ 7=週日） |
| start_time | DateTime | NOT NULL | 起始時間 |
| end_time | DateTime | NOT NULL | 結束時間 |

#### 6.2.7 Conversations（對話）

| 欄位 | 資料型態 | 限制 | 說明 |
|------|---------|------|------|
| conversation_id | AutoNumber | PK | 主鍵 |
| user_a_id | Long Integer | FK → Users, NOT NULL | 對話者 A |
| user_b_id | Long Integer | FK → Users, NOT NULL | 對話者 B |
| created_at | DateTime | NOT NULL | 建立時間 |
| last_message_at | DateTime | | 最後訊息時間（供排序用） |

**限制**：同一對 `(user_a_id, user_b_id)` 僅允許存在一筆紀錄。查詢時需同時考慮 `(A, B)` 與 `(B, A)` 之組合。

#### 6.2.8 Messages（訊息）

| 欄位 | 資料型態 | 限制 | 說明 |
|------|---------|------|------|
| message_id | AutoNumber | PK | 主鍵 |
| conversation_id | Long Integer | FK → Conversations, NOT NULL | 所屬對話 |
| sender_user_id | Long Integer | FK → Users, NOT NULL | 發送者 |
| content | Memo | NOT NULL | 訊息內容（純文字） |
| sent_at | DateTime | NOT NULL | 發送時間 |

#### 6.2.9 Matches（媒合配對與合約條款）

| 欄位 | 資料型態 | 限制 | 說明 |
|------|---------|------|------|
| match_id | AutoNumber | PK | 主鍵 |
| tutor_id | Long Integer | FK → Tutors, NOT NULL | 老師 |
| student_id | Long Integer | FK → Students, NOT NULL | 學生 |
| subject_id | Long Integer | FK → Subjects, NOT NULL | 科目 |
| status | Text(15) | NOT NULL, DEFAULT 'pending' | 當前狀態 |
| invite_message | Memo | | 家長邀請留言 |
| want_trial | Yes/No | DEFAULT No | 是否試教 |
| hourly_rate | Currency | | 正式時薪 |
| sessions_per_week | Integer | | 每週堂數 |
| start_date | Date | | 合約起始日期 |
| end_date | Date | | 合約結束日期 |
| penalty_amount | Currency | | 違約金 |
| trial_price | Currency | | 試教價格 |
| trial_count | Integer | | 試教次數 |
| contract_notes | Memo | | 附加條款 |
| terminated_by | Long Integer | FK → Users | 提出終止之使用者 |
| termination_reason | Memo | | 終止原因 |
| created_at | DateTime | NOT NULL | 建立時間 |
| updated_at | DateTime | NOT NULL | 最後狀態變更時間 |

#### 6.2.10 Sessions（上課日誌）

| 欄位 | 資料型態 | 限制 | 說明 |
|------|---------|------|------|
| session_id | AutoNumber | PK | 主鍵 |
| match_id | Long Integer | FK → Matches, NOT NULL | 所屬配對 |
| session_date | Date | NOT NULL | 上課日期 |
| hours | Double | NOT NULL | 時數 |
| content_summary | Memo | NOT NULL | 內容摘要 |
| homework | Memo | | 指派作業 |
| student_performance | Memo | | 學生當堂表現 |
| next_plan | Memo | | 下次預計進度 |
| visible_to_parent | Yes/No | DEFAULT No | 是否公開予家長 |
| created_at | DateTime | NOT NULL | 建立時間 |
| updated_at | DateTime | NOT NULL | 最後修改時間 |

#### 6.2.11 Session_Edit_Logs（日誌修改歷史）

| 欄位 | 資料型態 | 限制 | 說明 |
|------|---------|------|------|
| log_id | AutoNumber | PK | 主鍵 |
| session_id | Long Integer | FK → Sessions, NOT NULL | 對應日誌 |
| field_name | Text(50) | NOT NULL | 被修改之欄位名稱 |
| old_value | Memo | | 修改前內容 |
| new_value | Memo | | 修改後內容 |
| edited_at | DateTime | NOT NULL | 修改時間 |

#### 6.2.12 Exams（考試紀錄）

| 欄位 | 資料型態 | 限制 | 說明 |
|------|---------|------|------|
| exam_id | AutoNumber | PK | 主鍵 |
| student_id | Long Integer | FK → Students, NOT NULL | 學生 |
| subject_id | Long Integer | FK → Subjects, NOT NULL | 科目 |
| added_by_user_id | Long Integer | FK → Users, NOT NULL | 新增者 |
| exam_date | Date | NOT NULL | 考試日期 |
| exam_type | Text(20) | NOT NULL | `段考` / `模考` / `隨堂考` |
| score | Double | NOT NULL | 分數 |
| visible_to_parent | Yes/No | DEFAULT No | 是否公開予家長 |
| created_at | DateTime | NOT NULL | 建立時間 |

#### 6.2.13 Reviews（三向評價）

| 欄位 | 資料型態 | 限制 | 說明 |
|------|---------|------|------|
| review_id | AutoNumber | PK | 主鍵 |
| match_id | Long Integer | FK → Matches, NOT NULL | 對應配對 |
| reviewer_user_id | Long Integer | FK → Users, NOT NULL | 評價者 |
| review_type | Text(20) | NOT NULL | `parent_to_tutor` / `tutor_to_student` / `tutor_to_parent` |
| rating_1 | Integer | NOT NULL, 1–5 | 維度一 |
| rating_2 | Integer | NOT NULL, 1–5 | 維度二 |
| rating_3 | Integer | 1–5 | 維度三（可為空值） |
| rating_4 | Integer | 1–5 | 維度四（可為空值） |
| personality_comment | Memo | | 性格評價 |
| comment | Memo | | 整體評論 |
| created_at | DateTime | NOT NULL | 建立時間 |
| updated_at | DateTime | | 最後修改時間 |

**唯一限制**：同一 `(match_id, reviewer_user_id, review_type)` 組合僅允許存在一筆紀錄。

### 6.3 關聯圖摘要

```
Users ──1:1───→ Tutors                    （帳號延伸）
Users ──1:N───→ Students                  （家長之子女）
Tutors ──M:N──→ Subjects                  （透過 Tutor_Subjects，含各科時薪）
Tutors ──1:N──→ Tutor_Availability        （可用時段）
Users ──M:N───→ Users                     （透過 Conversations）
Conversations ─1:N─→ Messages             （對話訊息）
Tutors ──1:N──→ Matches                   （老師之配對）
Students ─1:N─→ Matches                   （學生之配對）
Subjects ─1:N─→ Matches                   （配對科目）
Matches ──1:N─→ Sessions                  （上課日誌）
Sessions ─1:N─→ Session_Edit_Logs         （修改歷史）
Matches ──1:N─→ Reviews                   （評價）
Students ─1:N─→ Exams                     （考試紀錄）
```

---

## 7. API 端點規格

所有 API 端點之基礎路徑為 `/api`。FastAPI 自動於 `/docs` 路徑生成 Swagger UI 互動式文件。

### 7.1 Auth（認證）

| Method | Path | 說明 | 權限 |
|--------|------|------|------|
| POST | `/api/auth/register` | 使用者註冊 | 公開 |
| POST | `/api/auth/login` | 使用者登入，回傳 JWT Token | 公開 |
| GET | `/api/auth/me` | 取得目前登入者資訊 | 需登入 |

### 7.2 Tutors（老師）

| Method | Path | 說明 | 權限 |
|--------|------|------|------|
| GET | `/api/tutors` | 搜尋老師列表 | 需登入 |
| GET | `/api/tutors/{id}` | 老師詳情（含評分、接案狀態、時段） | 需登入 |
| PUT | `/api/tutors/{id}` | 更新個人資料 | 老師本人 |
| PUT | `/api/tutors/{id}/availability` | 更新可用時段 | 老師本人 |
| PUT | `/api/tutors/{id}/visibility` | 更新欄位公開設定 | 老師本人 |

**GET `/api/tutors` 查詢參數**

| 參數 | 型態 | 說明 |
|------|------|------|
| subject_id | Integer | 篩選可教授指定科目之老師 |
| min_rate | Float | 時薪下限 |
| max_rate | Float | 時薪上限 |
| min_rating | Float | 評分門檻 |
| school | String | 學校名稱（模糊比對） |
| sort_by | String | 排序方式：`rating` / `rate_asc` / `newest` |
| page | Integer | 頁碼（預設 1） |
| page_size | Integer | 每頁筆數（預設 20） |

### 7.3 Students（學生）

| Method | Path | 說明 | 權限 |
|--------|------|------|------|
| GET | `/api/students` | 取得學生列表 | 家長（自己子女）或老師（配對學生） |
| POST | `/api/students` | 新增子女 | 家長 |
| PUT | `/api/students/{id}` | 更新學生資料 | 家長（該子女之家長） |

### 7.4 Messages（訊息）

| Method | Path | 說明 | 權限 |
|--------|------|------|------|
| GET | `/api/conversations` | 取得對話列表 | 需登入 |
| POST | `/api/conversations` | 開啟新對話 | 需登入 |
| GET | `/api/conversations/{id}/messages` | 取得訊息（分頁） | 對話參與者 |
| POST | `/api/conversations/{id}/messages` | 發送訊息 | 對話參與者 |

### 7.5 Matches（媒合）

| Method | Path | 說明 | 權限 |
|--------|------|------|------|
| POST | `/api/matches` | 送出邀請 | 家長 |
| GET | `/api/matches` | 取得配對列表（可篩選 status） | 需登入 |
| GET | `/api/matches/{id}` | 配對詳情 | 配對參與者 |
| PATCH | `/api/matches/{id}/status` | 狀態轉換 | 依狀態機規則 |

**PATCH `/api/matches/{id}/status` 請求格式**

```json
{
  "action": "accept | reject | cancel | confirm_trial | reject_trial | pause | resume | terminate | agree_terminate | disagree_terminate",
  "reason": "終止原因（僅 terminate 時需要）"
}
```

### 7.6 Sessions（上課日誌）

| Method | Path | 說明 | 權限 |
|--------|------|------|------|
| GET | `/api/matches/{match_id}/sessions` | 取得日誌列表 | 配對參與者（家長依 visible_to_parent 過濾） |
| POST | `/api/matches/{match_id}/sessions` | 新增日誌 | 老師 |
| PUT | `/api/sessions/{id}` | 修改日誌（留修改歷史） | 老師 |
| GET | `/api/sessions/{id}/edit-logs` | 查看修改歷史 | 配對參與者 |

### 7.7 Exams（考試紀錄）

| Method | Path | 說明 | 權限 |
|--------|------|------|------|
| GET | `/api/students/{student_id}/exams` | 取得考試清單 | 配對參與者（依權限過濾） |
| POST | `/api/students/{student_id}/exams` | 新增考試紀錄 | 老師或家長 |
| PUT | `/api/exams/{id}` | 修改考試紀錄 | 新增者 |

### 7.8 Reviews（評價）

| Method | Path | 說明 | 權限 |
|--------|------|------|------|
| GET | `/api/tutors/{tutor_id}/reviews` | 取得老師之評價列表 | 需登入 |
| GET | `/api/matches/{match_id}/reviews` | 取得配對之所有評價（三向） | 配對參與者 |
| POST | `/api/matches/{match_id}/reviews` | 撰寫評價 | 配對參與者（match 須為 ended） |
| PUT | `/api/reviews/{id}` | 修改評價 | 評價者本人（7 日內） |

### 7.9 Stats（統計）

| Method | Path | 說明 | 權限 |
|--------|------|------|------|
| GET | `/api/stats/income` | 老師收入統計 | 老師 |
| GET | `/api/stats/expense` | 家長支出統計 | 家長 |
| GET | `/api/stats/student-progress/{student_id}` | 學生成績趨勢 | 配對參與者 |

**查詢參數**

| 參數 | 適用端點 | 說明 |
|------|---------|------|
| group_by | income, expense | `month` / `student` / `subject`（收入）；`month` / `child` / `subject`（支出） |

### 7.10 Admin（系統管理）

所有 Admin 端點均要求 `role = admin`。

| Method | Path | 說明 |
|--------|------|------|
| GET | `/api/admin/users` | 取得所有使用者帳號列表 |
| GET | `/api/admin/system-status` | 取得系統統計數據 |
| POST | `/api/admin/export/{table_name}` | 匯出指定表為 CSV（背景任務）→ 回傳 task_id |
| POST | `/api/admin/import/{table_name}` | 匯入 CSV 至指定表（背景任務）→ 回傳 task_id |
| POST | `/api/admin/export-all` | 一鍵匯出全部資料表 |
| POST | `/api/admin/import-all` | 一鍵匯入全部資料表 |
| POST | `/api/admin/seed` | 觸發假資料生成 |
| POST | `/api/admin/reset` | 清空資料庫（保留 Admin 帳號與表結構） |
| GET | `/api/admin/tasks/{task_id}` | 查詢背景任務執行狀態 |

---

## 8. 前端頁面與路由規格

### 8.1 路由表

```
/login                              → 登入頁
/register                           → 註冊頁

# 共用
/messages                           → 對話列表
/messages/:conversation_id          → 對話頁面

# 家長端（需登入，role = parent）
/parent/dashboard                   → 家長首頁
/parent/search                      → 搜尋老師
/parent/tutor/:id                   → 老師詳情頁
/parent/students                    → 子女管理
/parent/match/:id                   → 配對詳情
/parent/expense                     → 支出統計

# 老師端（需登入，role = tutor）
/tutor/dashboard                    → 老師首頁
/tutor/profile                      → 個人檔案編輯
/tutor/match/:id                    → 配對詳情
/tutor/income                       → 收入統計

# Admin（需登入，role = admin）
/admin/dashboard                    → 系統管理後台
```

### 8.2 重要元件清單

| 元件 | 說明 | 使用頁面 |
|------|------|---------|
| TutorCard.vue | 老師搜尋結果卡片 | SearchView |
| TutorFilter.vue | 搜尋篩選與排序控制 | SearchView |
| AvailabilityCalendar.vue | 可用時段行事曆 | TutorDetailView、ProfileView |
| MatchStatusBadge.vue | 配對狀態標籤 | Dashboard、MatchDetailView |
| ContractForm.vue | 合約條款表單 | MatchDetailView |
| InviteForm.vue | 媒合邀請表單 | TutorDetailView |
| ReviewForm.vue | 評價表單（三向共用） | MatchDetailView |
| ReviewList.vue | 評價列表 | TutorDetailView、MatchDetailView |
| RadarChart.vue | 評價雷達圖 | TutorDetailView |
| SessionForm.vue | 上課日誌表單 | MatchDetailView |
| SessionTimeline.vue | 上課日誌時間軸 | MatchDetailView |
| IncomeChart.vue | 收入統計圖表 | IncomeView |
| ExpenseChart.vue | 支出統計圖表 | ExpenseView |
| ProgressChart.vue | 成績趨勢圖表 | MatchDetailView |

---

## 9. 非同步任務引擎規格

### 9.1 架構

本系統採用 huey 作為非同步任務引擎，以 SQLite 作為訊息佇列之 broker。huey worker 作為獨立 process 運行，與 FastAPI server 共用相同之 Python 環境與 Access 資料庫連線。

### 9.2 任務清單

| 任務 | 觸發方式 | 說明 |
|------|---------|------|
| `import_csv_task` | API 呼叫 | 匯入 CSV 至指定資料表（支援 upsert 與 overwrite 模式） |
| `export_csv_task` | API 呼叫 | 匯出指定資料表為 CSV 字串 |
| `generate_seed_data` | API 呼叫 | 生成假資料 CSV 並自動匯入 |
| `calculate_income_stats` | API 呼叫 | 計算老師收入統計 |
| `calculate_expense_stats` | API 呼叫 | 計算家長支出統計 |
| `lock_expired_reviews` | 定時排程（每日 03:00） | 標記超過 7 日之評價為不可修改 |

### 9.3 任務狀態查詢

前端透過 `GET /api/admin/tasks/{task_id}` 以 polling 方式查詢任務執行狀態。回應格式：

```json
{
  "success": true,
  "data": {
    "task_id": "abc123",
    "status": "pending | running | completed | failed",
    "result": { ... },
    "error": null
  }
}
```

### 9.4 程式碼範例

```python
# app/worker.py
from huey import SqliteHuey

huey = SqliteHuey(filename="data/huey.db")

from app.tasks import import_export, stats_tasks, seed_tasks, scheduled
```

```python
# app/tasks/import_export.py
from app.worker import huey
from app.database import get_connection
import csv, io

@huey.task()
def import_csv_task(table_name: str, csv_content: str, mode: str = "upsert"):
    """
    匯入 CSV 至 Access 資料表。
    參數：
        table_name: 目標資料表名稱
        csv_content: CSV 格式之字串內容
        mode: "upsert"（比對式更新）或 "overwrite"（清空後寫入）
    回傳：
        dict，包含 table、rows、mode 等資訊
    """
    conn = get_connection()
    reader = csv.DictReader(io.StringIO(csv_content))

    if mode == "overwrite":
        conn.cursor().execute(f"DELETE FROM [{table_name}]")

    row_count = 0
    for row in reader:
        if mode == "upsert":
            _upsert_row(conn, table_name, row)
        else:
            _insert_row(conn, table_name, row)
        row_count += 1

    conn.commit()
    conn.close()
    return {"table": table_name, "rows": row_count, "mode": mode}

@huey.task()
def export_csv_task(table_name: str) -> str:
    """匯出指定資料表之全部內容為 CSV 格式字串。"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM [{table_name}]")
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    for row in rows:
        writer.writerow(row)
    return output.getvalue()
```

```python
# app/tasks/stats_tasks.py
from app.worker import huey
from app.database import get_connection

@huey.task()
def calculate_income_stats(tutor_user_id: int, group_by: str = "month"):
    """
    計算指定老師之收入統計。
    參數：
        tutor_user_id: 老師之 user_id
        group_by: 分群維度，可為 "month"、"student"、"subject"
    回傳：
        list[dict]，各筆包含 period/label、total_income、total_hours 等欄位
    """
    conn = get_connection()
    cursor = conn.cursor()

    sql_map = {
        "month": """
            SELECT FORMAT(s.session_date, 'yyyy-mm') AS period,
                   SUM(s.hours * m.hourly_rate) AS total_income,
                   SUM(s.hours) AS total_hours,
                   COUNT(*) AS session_count
            FROM Sessions s
            INNER JOIN Matches m ON s.match_id = m.match_id
            INNER JOIN Tutors t ON m.tutor_id = t.tutor_id
            WHERE t.user_id = ?
            GROUP BY FORMAT(s.session_date, 'yyyy-mm')
            ORDER BY FORMAT(s.session_date, 'yyyy-mm') DESC
        """,
        "student": """
            SELECT st.name AS label,
                   SUM(s.hours * m.hourly_rate) AS total_income,
                   SUM(s.hours) AS total_hours
            FROM Sessions s
            INNER JOIN Matches m ON s.match_id = m.match_id
            INNER JOIN Students st ON m.student_id = st.student_id
            INNER JOIN Tutors t ON m.tutor_id = t.tutor_id
            WHERE t.user_id = ?
            GROUP BY st.name
        """,
        "subject": """
            SELECT sub.subject_name AS label,
                   SUM(s.hours * m.hourly_rate) AS total_income,
                   SUM(s.hours) AS total_hours
            FROM Sessions s
            INNER JOIN Matches m ON s.match_id = m.match_id
            INNER JOIN Subjects sub ON m.subject_id = sub.subject_id
            INNER JOIN Tutors t ON m.tutor_id = t.tutor_id
            WHERE t.user_id = ?
            GROUP BY sub.subject_name
        """
    }

    cursor.execute(sql_map[group_by], (tutor_user_id,))
    columns = [desc[0] for desc in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return rows
```

```python
# app/tasks/scheduled.py
from app.worker import huey
from datetime import datetime, timedelta
from app.database import get_connection

@huey.periodic_task(huey.crontab(hour="3", minute="0"))
def lock_expired_reviews():
    """
    定時任務：每日凌晨 03:00 執行。
    標記超過 7 日之評價為不可修改。
    實際鎖定邏輯於 API 端以時間差判斷，此任務可用於記錄日誌或執行額外清理。
    """
    conn = get_connection()
    cutoff = datetime.now() - timedelta(days=7)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) AS cnt FROM Reviews
        WHERE created_at < ? AND updated_at IS NOT NULL
    """, (cutoff,))
    result = cursor.fetchone()
    conn.close()

    import logging
    logger = logging.getLogger("app.tasks.scheduled")
    logger.info(f"評價鎖定檢查完成，共 {result[0]} 筆評價已超過修改期限")
```

---

## 10. 分工規劃

| 成員 | 負責範圍 | 交付物 |
|------|---------|--------|
| 技術負責人 | Access 資料表建立、FastAPI 後端開發、huey worker 建置、Vue 前端開發、假資料生成器撰寫 | 完整系統原始碼 |
| 組員 A | 簡報製作、上台口頭報告 | PowerPoint 簡報檔案 |
| 組員 B | 系統操作測試、書面報告撰寫（系統說明、功能截圖） | 書面報告文件 |
| 全體 | 展示前排練、測試情境腳本準備 | Demo 流程表 |

### 組員可執行之具體任務

- 使用 Admin 後台之假資料生成功能匯入測試資料後，按 demo 腳本操作系統並截圖記錄。
- 撰寫使用者操作手冊（按步驟截圖搭配文字說明）。
- 設計多組測試情境（老師暱稱、科目組合、評價內容等）。
- 測試各種狀態轉換之正確性（如試教後拒絕、暫停後恢復、終止流程等）。

---

## 11. 開發排程

預計開發週期為 5 週，以下依週次列示各階段之工作項目。

### 第 1 週：基礎建設

- [ ] 於 MS Access 中建立全部 13 張資料表及其關聯圖
- [ ] 初始化後端儲存庫：FastAPI 專案結構、pyodbc 連線驗證、config 組態、logging 設定
- [ ] 實作 BaseRepository 與 auth_repo
- [ ] 完成 Auth 模組：註冊、登入、JWT 簽發、Admin 帳號自動建立
- [ ] 初始化 huey worker，驗證任務派發與執行
- [ ] 初始化前端儲存庫：Vue + Router + Pinia + Axios 封裝
- [ ] 完成登入頁面與路由守衛
- [ ] 撰寫 start.bat 一鍵啟動腳本

### 第 2 週：核心業務流程

- [ ] 實作 tutor_repo、student_repo 與對應前端頁面
- [ ] 完成搜尋老師功能（篩選、排序、卡片列表、詳情頁）
- [ ] 完成老師個人檔案編輯（基本資料、可用時段、公開設定）
- [ ] 實作 match_repo 與完整狀態機 API（含所有狀態轉換）
- [ ] 實作 message_repo 與訊息系統前端 UI

### 第 3 週：教學管理

- [ ] 實作 session_repo（含 visible_to_parent、修改歷史記錄）
- [ ] 實作 exam_repo（含權限控制）
- [ ] 完成老師 Dashboard 與家長 Dashboard
- [ ] 建立 Admin 後台基本框架

### 第 4 週：評價、統計、匯入匯出

- [ ] 實作 review_repo 與前端評價元件（三向共用表單、雷達圖、七日修改期限）
- [ ] 實作 stats_repo 與前端圖表（收入統計、支出統計、成績趨勢）
- [ ] 實作 CSV 匯入匯出之 huey 背景任務
- [ ] 實作假資料生成器之 huey 背景任務
- [ ] 完成 Admin 後台全部功能（匯入匯出、清空、假資料、系統狀態）

### 第 5 週：收尾與交付

- [ ] 全系統端對端測試
- [ ] UI 視覺調整與細節修正
- [ ] 組員製作簡報、截取系統畫面、撰寫書面報告
- [ ] 全體進行展示排練

---

## 12. 展示流程

建議之展示流程約 10–15 分鐘，依以下順序進行。

### 12.1 技術架構展示（2 分鐘）

1. 開啟 Swagger UI（`http://localhost:8000/docs`），展示完整之 API 端點清單與互動式測試介面。
2. 開啟 MS Access，展示 13 張資料表之結構與關聯圖（滿足課程要求）。
3. 簡要說明系統架構：FastAPI + huey + Vue + Access 之分層設計。

### 12.2 Admin 操作展示（2 分鐘）

1. 以 Admin 帳號登入，進入系統管理後台。
2. 展示系統狀態面板（各類統計數據）。
3. 點擊「假資料生成」按鈕，展示 huey 背景任務之運作（UI 不阻塞，任務於背景執行）。
4. 資料生成完成後，展示系統已自動匯入資料。

### 12.3 家長操作展示（4 分鐘）

1. 以家長帳號註冊並登入，進入家長 Dashboard。
2. 新增子女資料。
3. 進入搜尋頁面，使用篩選條件（科目、時薪、評分）搜尋老師。
4. 點擊老師卡片進入詳情頁，檢視評價雷達圖與可用時段。
5. 點擊「傳送訊息」與老師溝通需求。
6. 點擊「送出邀請」，勾選試教選項並填寫留言。

### 12.4 老師操作展示（4 分鐘）

1. 切換至老師帳號登入，Dashboard 顯示新邀請通知。
2. 查看邀請詳情，接受邀請進入試教階段。
3. 試教完成，雙方確認後轉為正式上課。
4. 記錄一筆上課日誌（設定為公開予家長）。
5. 記錄一筆考試成績。

### 12.5 評價與統計展示（2 分鐘）

1. 結束配對，家長撰寫評價（含各維度評分與性格自由文字）。
2. 老師分別對學生與家長撰寫評價。
3. 展示老師收入統計圖表（切換月份/學生/科目分群）。
4. 展示家長支出統計。
5. 展示學生成績趨勢折線圖。

### 12.6 收尾亮點（1 分鐘）

1. 於 Admin 後台執行一鍵匯出全部資料為 CSV。
2. 切換至 MS Access，展示方才操作所產生之資料已確實寫入資料表。
3. 於 Swagger UI 直接對特定 API 發送測試請求，展示 JSON 回應結構。

---

## 13. 附錄

### 13.1 可選之擴充功能

以下功能不在本版本之必要範圍內，可視開發進度評估是否納入。

| 功能 | 說明 |
|------|------|
| Access 報表功能 | 於 Access 內建置月收入報表，展示 Access 之進階功能 |
| 大頭照上傳 | 老師個人檔案支援上傳照片 |
| 已讀未讀標記 | 訊息系統加入已讀標記與未讀訊息計數 |
| 即時通知 | Dashboard 即時顯示通知（新邀請、新訊息、配對狀態變更） |
| 暗色模式 | 前端支援深色主題切換 |
| 日曆檢視 | 上課日誌以日曆形式呈現 |

### 13.2 已知限制

| 限制 | 說明 |
|------|------|
| MS Access ODBC Driver | 僅支援 Windows 作業系統，無法於 macOS 或 Linux 環境下運行 |
| MS Access 分頁查詢 | Access SQL 不支援 `LIMIT` / `OFFSET` 語法，分頁於 Python 端處理 |
| MS Access 並行存取 | Access 對多執行緒並行寫入之支援有限，高並發場景可能產生鎖定問題 |
| 非即時通訊 | 訊息系統採 HTTP polling 模式，非 WebSocket 即時推播 |
| 不部署上線 | 系統設計為本機運行，未考慮生產環境之安全性與效能優化 |

---

*文件結束*
