# 家教媒合與評價平台 系統規格書

**文件編號**：TMP-SPEC-2026-001
**版本**：v5.0
**建立日期**：2026 年 3 月 28 日
**最後更新**：2026 年 3 月 29 日

---

## 閱讀指引

本文件依讀者背景分為兩個段落：

| 段落 | 適用對象 | 內容風格 |
|------|---------|---------|
| **第 1~5 節** | 全體組員 | 系統的功能與運作方式 |
| **第 6~13 節** | 技術開發者 | 資料庫欄位、API 規格、程式碼範例等技術細節，供開發時查閱 |

> 對於不想讀技術細節的同學，**閱讀第 1~5 節即可掌握系統全貌**。第 6 節以後可視需要再行查閱。

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

### 1.1 專案簡介

本專案是一個**家教媒合網站**，定位類似「家教版的 104 人力銀行」。

以一個典型的使用情境為例：某位家長希望為孩子尋找數學家教，於系統中輸入「數學、時薪 500~800 元」等條件後，系統列出符合條件的老師。家長參考老師的自我介紹與歷史評價後，透過站內訊息進一步溝通，隨後發出媒合邀請。老師收到邀請後可選擇接受或拒絕，接受後即進入正式教學階段。教學結束後，雙方可互相評價。

系統的三大核心功能如下：

| 核心功能 | 說明 |
|---------|------|
| **媒合** | 家長搜尋老師 → 訊息溝通 → 發送邀請 → 老師接受 → 開始上課 |
| **教學管理** | 老師記錄上課日誌與考試成績，家長可依權限查閱孩子的學習狀況 |
| **三向評價** | 合作結束後，家長可評老師，老師可評學生及家長 |

### 1.2 課程背景

本專案為 **SQL（MS Access）通識課**之期末分組專題。課程要求如下：

- 須使用 **MS Access** 作為資料庫（即所有資料的儲存位置）
- 學期末須**上台報告**並**現場操作展示**系統功能

### 1.3 設計目標

| 目標 | 說明 |
|------|------|
| 滿足課程要求 | 使用 MS Access 作為資料庫，資料表與關聯圖可於 Access 中直接展示 |
| 嘗試業界實踐 | 採用三層式架構、RESTful API、JWT 認證等常見做法，希望藉此提升專題的技術深度 |
| 本機運行即可 | 全部服務運行於本機環境，展示時於本機操作，不做線上部署 |

### 1.4 專案時程

預計開發期間為 **5 週以上**。最終交付形式為上台報告，搭配系統現場操作展示。

---

## 2. 系統架構

### 2.1 架構概覽

本系統由三個程式組成，同時運行於同一台 Windows 電腦上。以餐廳作為類比：前端相當於「點餐櫃台」（使用者看到的畫面），後端相當於「廚房」（處理所有業務邏輯），Access 資料庫相當於「倉庫」（儲存所有資料），另有一個背景任務處理器（相當於負責雜務的人員）負責執行較耗時的工作。

```
+----------+          +----------+          +----------+
|          |  HTTP /  |          |  ODBC /  |          |
| Vue 前端  | -------> | FastAPI  | -------> | MS       |
| (瀏覽器)  | <------- | 後端     | <------- | Access   |
|          |  JSON    |          |  pyodbc  | 資料庫    |
+----------+          +-----+----+          +----------+
 點餐櫃台               廚房 |                  倉庫 ^
                             |                       |
                             | 派工作         讀寫資料 |
                             v                       |
                       +----------+                  |
                       | huey     | -----------------+
                       | worker   |
                       | 背景雜務  |
                       +----------+
                        匯入匯出、報表計算、
                        假資料生成等耗時工作

  三個程式皆運行於本機，透過 start.bat 一鍵啟動
```

### 2.2 三個程式的職責

| 程式 | 使用技術 | 職責 |
|------|---------|------|
| **前端（Vue）** | Vue 3 + Vite | 使用者在瀏覽器中看到的所有畫面，包含登入頁、搜尋頁、聊天室等 |
| **後端（FastAPI）** | Python FastAPI | 系統的核心邏輯層，負責登入驗證、老師搜尋、配對邀請、資料寫入等所有處理 |
| **背景任務（huey）** | Python huey | 負責執行匯入匯出 CSV、產生假資料、計算統計報表等較耗時的工作，避免阻塞使用者畫面 |

### 2.3 為什麼分成三個程式？

以便利商店結帳為例：若店員一邊結帳、一邊又要去後方加熱餐點，顧客就必須等待。因此合理的做法是讓店員專心結帳（後端），另一位人員負責加熱（背景任務），顧客則只需關注螢幕上的金額（前端）。三者各司其職，互不阻塞。

### 2.4 技術清單

以下列出本專案使用的技術。此處僅提供概覽，不需要全部記住：

| 類別 | 技術名稱 | 簡要說明 |
|------|---------|---------|
| 前端畫面 | Vue 3 | 用於建構網頁畫面的框架，成果運行於瀏覽器中 |
| 前端打包 | Vite | 負責打包前端程式碼並啟動開發伺服器 |
| 頁面切換 | Vue Router | 控制頁面之間的跳轉邏輯 |
| 前端資料管理 | Pinia | 在不同頁面之間共享資料，例如「目前登入的使用者是誰」 |
| 前端呼叫後端 | Axios | 前端用來向後端發送請求的工具 |
| 後端框架 | FastAPI | 以 Python 撰寫的後端框架，負責接收前端的請求並回傳結果 |
| 資料驗證 | Pydantic | 確保前端傳來的資料格式正確，例如「分數必須是數字」 |
| 登入驗證 | JWT + bcrypt | JWT 是登入後取得的「通行證」，後續每次操作皆須攜帶以證明身份；bcrypt 負責將密碼加密後儲存 |
| 資料庫連線 | pyodbc | Python 透過此工具與 MS Access 資料庫溝通 |
| 資料庫 | MS Access | 儲存所有資料的關聯式資料庫（課程要求使用） |
| 背景任務 | huey + SQLite | huey 是輕量的任務排隊系統，SQLite 作為其記錄待辦任務的小型資料庫 |
| 環境設定 | .env 檔案 | 系統的設定檔，用於存放密碼、資料庫路徑等不適合寫死在程式碼中的資訊 |
| 日誌記錄 | Python logging | 自動記錄系統運行中的事件，便於事後追查問題 |

---

## 3. 技術架構詳細設計

> **提示：** 本節包含較多程式碼，主要供開發者撰寫程式時參考。非技術組員可僅閱讀各段開頭的說明文字，程式碼區塊可跳過。

### 3.1 原始碼目錄結構

程式碼分為兩個獨立的資料夾（儲存庫）：一個存放後端（Python），一個存放前端（Vue）。概念上類似將廚房用品與外場用品分開管理。

#### 3.1.1 後端資料夾：`tutor-platform-api`

以下樹狀圖列出後端所有檔案與資料夾，各檔案旁附有用途說明。

```
tutor-platform-api/
├── .env                              # 設定檔（密碼、路徑等，不納入版控）
├── .env.example                      # 設定檔範本（告知需填寫哪些設定）
├── requirements.txt                  # Python 套件依賴清單
├── start.bat                         # 一鍵啟動腳本
├── README.md                         # 專案說明文件
│
├── app/                              # [主要程式碼]
│   ├── main.py                       # 程式入口——啟動後端伺服器
│   ├── config.py                     # 讀取 .env 設定檔
│   ├── database.py                   # 負責建立與 MS Access 資料庫的連線
│   ├── dependencies.py               # 共用的依賴注入定義
│   ├── exceptions.py                 # 定義錯誤類型（找不到資源、無權限等）
│   ├── worker.py                     # 背景任務處理器的啟動入口
│   │
│   ├── models/                       # [資料格式定義]
│   │   │                             #  定義各類請求與回應的資料結構
│   │   ├── common.py                 # 統一回應格式
│   │   ├── auth.py                   # 登入/註冊相關
│   │   ├── tutor.py                  # 老師相關
│   │   ├── student.py                # 學生相關
│   │   ├── match.py                  # 媒合配對相關
│   │   ├── session.py                # 上課日誌相關
│   │   ├── exam.py                   # 考試紀錄相關
│   │   ├── review.py                 # 評價相關
│   │   ├── message.py                # 訊息相關
│   │   └── stats.py                  # 統計數據相關
│   │
│   ├── repositories/                 # [資料存取層]
│   │   │                             #  所有與資料庫溝通的程式碼皆集中於此
│   │   ├── base.py                   # 共用的基本功能（查詢、新增、修改）
│   │   ├── auth_repo.py              # 帳號相關的資料庫操作
│   │   ├── tutor_repo.py             # 老師相關
│   │   ├── student_repo.py           # 學生相關
│   │   ├── match_repo.py             # 媒合配對相關
│   │   ├── session_repo.py           # 上課日誌相關
│   │   ├── exam_repo.py              # 考試紀錄相關
│   │   ├── review_repo.py            # 評價相關
│   │   ├── message_repo.py           # 訊息相關
│   │   └── stats_repo.py             # 統計相關
│   │
│   ├── routers/                      # [API 路由層]
│   │   │                             #  定義網址與功能的對應關係
│   │   ├── auth.py                   # /api/auth/... 登入註冊
│   │   ├── tutors.py                 # /api/tutors/... 老師相關
│   │   ├── students.py               # /api/students/... 學生相關
│   │   ├── matches.py                # /api/matches/... 媒合配對
│   │   ├── sessions.py               # /api/sessions/... 上課日誌
│   │   ├── exams.py                  # /api/exams/... 考試紀錄
│   │   ├── reviews.py                # /api/reviews/... 評價
│   │   ├── messages.py               # /api/messages/... 訊息
│   │   ├── stats.py                  # /api/stats/... 統計
│   │   └── admin.py                  # /api/admin/... 管理員專用
│   │
│   ├── tasks/                        # [背景任務] 較耗時的工作放置於此
│   │   ├── import_export.py          # CSV 檔案的匯入和匯出
│   │   ├── stats_tasks.py            # 統計報表的計算
│   │   ├── seed_tasks.py             # 假資料生成
│   │   └── scheduled.py              # 定時執行的任務（如每日凌晨 3 點檢查過期評價）
│   │
│   └── utils/                        # [工具函式] 輔助用的小型程式
│       ├── security.py               # 密碼加密、JWT 的產生與驗證
│       ├── csv_handler.py            # CSV 檔案讀寫
│       └── logger.py                 # 日誌組態
│
├── logs/                             # 日誌檔案存放處
│   └── app.log
│
├── data/
│   ├── tutoring.accdb                # [重要] MS Access 資料庫檔案
│   └── huey.db                       # 背景任務的排隊紀錄
│
└── seed/
    ├── generator.py                  # 假資料產生邏輯
    └── output/                       # 產生之 CSV 暫存目錄
```

#### 3.1.2 前端資料夾：`tutor-platform-web`

```
tutor-platform-web/
├── .env                              # 設定（如後端的網址）
├── package.json                      # 前端套件依賴清單
├── vite.config.js                    # 前端打包設定
│
└── src/                              # [主要程式碼]
    ├── main.js                       # 前端程式入口
    ├── App.vue                       # 最外層的畫面框架
    │
    ├── router/                       # [頁面路由] 定義網址與頁面的對應
    │   └── index.js
    │
    ├── stores/                       # [全域狀態管理] 跨頁面共享的資料
    │   ├── auth.js                   # 登入狀態（目前登入者的資訊）
    │   ├── tutor.js                  # 老師搜尋結果的暫存
    │   ├── match.js                  # 配對狀態
    │   └── message.js                # 訊息狀態
    │
    ├── api/                          # [後端溝通層] 封裝所有 API 呼叫
    │   ├── index.js                  # 統一設定（自動攜帶通行證等）
    │   ├── auth.js                   # 登入/註冊 API
    │   ├── tutors.js                 # 老師相關 API
    │   ├── matches.js                # 媒合相關 API
    │   ├── sessions.js               # 上課日誌 API
    │   ├── exams.js                  # 考試紀錄 API
    │   ├── reviews.js                # 評價 API
    │   ├── messages.js               # 訊息 API
    │   ├── stats.js                  # 統計 API
    │   └── admin.js                  # 管理員 API
    │
    ├── views/                        # [頁面級元件] 各個獨立頁面
    │   ├── LoginView.vue             # 登入頁
    │   ├── RegisterView.vue          # 註冊頁
    │   ├── parent/                   # 家長端頁面
    │   │   ├── DashboardView.vue     #   家長首頁
    │   │   ├── SearchView.vue        #   搜尋老師
    │   │   ├── TutorDetailView.vue   #   老師詳情
    │   │   ├── StudentsView.vue      #   管理子女
    │   │   ├── MatchDetailView.vue   #   配對詳情
    │   │   └── ExpenseView.vue       #   支出統計
    │   ├── tutor/                    # 老師端頁面
    │   │   ├── DashboardView.vue     #   老師首頁
    │   │   ├── ProfileView.vue       #   編輯個人檔案
    │   │   ├── MatchDetailView.vue   #   配對詳情
    │   │   └── IncomeView.vue        #   收入統計
    │   ├── messages/                 # 訊息相關頁面
    │   │   ├── ConversationListView.vue  # 對話列表
    │   │   └── ChatView.vue              # 聊天頁面
    │   └── admin/                    # 管理員頁面
    │       └── AdminDashboardView.vue    # 管理後台
    │
    └── components/                   # [可重用元件] 各頁面共用的畫面零件
        ├── common/                   #   共用元件（頂部選單、側邊欄、載入動畫）
        ├── tutor/                    #   老師相關元件（搜尋卡片、篩選器、行事曆）
        ├── match/                    #   配對相關元件（狀態標籤、合約表單）
        ├── review/                   #   評價相關元件（評分表單、雷達圖）
        ├── session/                  #   上課日誌元件（表單、時間軸）
        └── stats/                    #   統計圖表元件（收入圖、支出圖、成績趨勢圖）
```

### 3.2 統一 API 回應格式

前端每次向後端發出請求時，後端皆以**統一格式**回應。無論請求內容為何，回應結構都包含三個欄位：是否成功、回傳資料、補充訊息。此設計使前端能以一致的方式處理所有回應。

回應結構如下：

```json
{
  "success": true 或 false,
  "data": 回傳資料（成功時）或 null（失敗時）,
  "message": 補充訊息（通常失敗時才有，例如「該老師目前不接受新學生」）
}
```

**成功範例**——登入後取得使用者資訊：
```json
{
  "success": true,
  "data": { "user_id": 1, "role": "tutor", "display_name": "王小明" },
  "message": null
}
```

**失敗範例**——操作不被允許：
```json
{
  "success": false,
  "data": null,
  "message": "該老師目前不接受新學生"
}
```

**分頁查詢範例**——共 87 筆結果，目前為第 1 頁：
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

<details>
<summary>技術細節（開發者展開）</summary>

#### 回應結構定義

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

#### 統一錯誤處理

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

</details>

### 3.3 Repository Pattern——資料存取方式

本系統採用 Repository Pattern 管理資料存取。以圖書館為類比：讀者不需要自行進入書庫翻找，只需告訴館員所需的書籍，由館員代為處理。

在系統中，各 Repository 類別即扮演「館員」的角色。後端的路由層（Router）需要資料時，不直接撰寫 SQL 查詢資料庫，而是呼叫對應的 Repository 方法。此設計有以下好處：

- SQL 語句集中於同一層，便於維護
- 若日後需更換資料庫引擎，僅需修改 Repository 層
- 各層職責明確，程式碼不易混雜

<details>
<summary>技術細節（開發者展開）</summary>

#### BaseRepository

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

#### Repository 使用範例

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
        sql = """
            SELECT COUNT(*) AS cnt
            FROM Matches
            WHERE tutor_id = ? AND status IN ('active', 'trial')
        """
        result = self.fetch_one(sql, (tutor_id,))
        return result["cnt"] if result else 0
```

#### Router 層呼叫規範

Router 層的職責：接收請求 → 驗證參數 → 呼叫 Repository → 封裝回應。不得包含 SQL 語句或複雜業務邏輯。

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
        if not t.pop("show_university"):
            t.pop("university", None)
        if not t.pop("show_department"):
            t.pop("department", None)

    return ApiResponse(success=True, data=tutors)
```

</details>

### 3.4 資料庫連線管理

每次前端發出請求時，後端會建立一條通往 Access 資料庫的連線，處理完畢後立即關閉，以避免資源浪費。類似於前往圖書館借書——進門、借書、出門，不長時間佔用座位。

<details>
<summary>技術細節（開發者展開）</summary>

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

</details>

### 3.5 環境變數管理

部分資訊不適合直接寫死在程式碼中（例如密碼、資料庫路徑），因此統一存放於 `.env` 設定檔，程式啟動時自動讀取。

專案中附有 `.env.example` 範本檔，列出所有需要填寫的欄位。取得專案後，將其複製並改名為 `.env`，再依環境填入對應的值即可。

| 設定項目 | 範例值 | 說明 |
|---------|--------|------|
| ACCESS_DB_PATH | data/tutoring.accdb | Access 資料庫檔案的路徑 |
| JWT_SECRET_KEY | your-secret-key-here | 用來加密通行證的密鑰 |
| JWT_EXPIRE_MINUTES | 60 | 登入後通行證的有效時間（分鐘） |
| ADMIN_USERNAME | admin | 管理員帳號 |
| ADMIN_PASSWORD | change-me | 管理員密碼 |
| LOG_LEVEL | INFO | 日誌記錄的詳細程度 |

<details>
<summary>技術細節（開發者展開）</summary>

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

</details>

### 3.6 系統日誌

系統會自動將運行過程中的事件記錄至 log 檔案，包含「誰在什麼時間做了什麼事」。當系統出現問題時，可開啟 log 檔案回溯事發經過，功能類似便利商店的監視器錄影。

日誌格式範例：

```
2026-04-15 14:23:01 | INFO     | 使用者 john_parent 登入成功
2026-04-15 14:23:05 | WARNING  | 配對 #42 狀態轉換被拒絕：trial → paused 不合法
2026-04-15 14:24:00 | INFO     | CSV 匯入完成：Users 表，共 25 筆
2026-04-15 14:25:30 | ERROR    | SQL 執行失敗：INSERT INTO Sessions ... [詳細錯誤]
```

每一行包含時間、嚴重程度（INFO = 正常資訊、WARNING = 警告、ERROR = 錯誤），以及事件描述。

<details>
<summary>技術細節（開發者展開）</summary>

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

</details>

### 3.7 一鍵啟動

無需逐一手動啟動三個程式。雙擊 `start.bat` 即可自動啟動後端、背景任務處理器與前端開發伺服器。

啟動完成後會顯示以下資訊：

```
================================================
  全部服務啟動完成

  API Server:   http://localhost:8000
  Swagger UI:   http://localhost:8000/docs     <- 所有 API 的互動式文件
  前端介面:     http://localhost:5173           <- 於瀏覽器開啟即可使用系統
================================================
```

<details>
<summary>技術細節（開發者展開）</summary>

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

</details>

### 3.8 前端 API 呼叫的統一封裝

前端每次向後端請求資料時，皆需執行幾項重複動作：攜帶登入通行證、檢查回應是否成功、處理登入過期的情況。這些共通邏輯統一封裝於 Axios interceptor 中，各頁面呼叫 API 時無需重複撰寫。

概念上類似公文流程的統一規範——蓋章、編號、歸檔等步驟由行政部門統一處理，各部門無需自行記住。

<details>
<summary>技術細節（開發者展開）</summary>

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

</details>

---

## 4. 角色與權限模型

### 4.1 三種使用者角色

本系統定義三種角色，各有不同的權限範圍。類似於學校中「校長」、「老師」、「家長」各有不同的可進入區域與可執行事項。

| 角色 | 帳號建立方式 | 職責說明 |
|------|------------|---------|
| **管理員（Super Admin）** | 系統啟動時自動建立（帳密設定於 `.env` 中） | 管理整個系統——匯入匯出資料、產生假資料、監控系統狀態，相當於網站的站長 |
| **家長（Parent）** | 自行於註冊頁面建立 | 需求端——搜尋老師、管理子女資料、發送媒合邀請、撰寫評價 |
| **家教老師（Tutor）** | 自行於註冊頁面建立 | 供給端——管理個人檔案、接受或拒絕邀請、記錄上課日誌與考試成績 |

### 4.2 權限對照表

下表列出各功能對應的角色權限。

| 功能 | 管理員 | 家長 | 老師 |
|------|:------:|:----:|:----:|
| 系統管理後台 | ✓ | ✗ | ✗ |
| 匯入匯出資料 | ✓ | ✗ | ✗ |
| 產生假資料 | ✓ | ✗ | ✗ |
| 清空資料庫 | ✓ | ✗ | ✗ |
| 查看所有帳號 | ✓ | ✗ | ✗ |
| 搜尋老師 | ✓ | ✓ | ✗ |
| 管理子女資料 | ✗ | ✓ | ✗ |
| 發送媒合邀請 | ✗ | ✓ | ✗ |
| 接受/拒絕邀請 | ✗ | ✗ | ✓ |
| 撰寫上課日誌 | ✗ | ✗ | ✓ |
| 查看上課日誌 | ✗ | 依老師是否設為公開 | ✓（自己的） |
| 新增考試成績 | ✗ | ✓ | ✓ |
| 查看考試成績 | ✗ | 依老師是否設為公開 | ✓（自己的） |
| 撰寫評價 | ✗ | ✓（評老師） | ✓（評學生 + 評家長） |
| 傳送訊息 | ✓ | ✓ | ✓ |
| 查看收入統計 | ✗ | ✗ | ✓（自己的） |
| 查看支出統計 | ✗ | ✓（自己的） | ✗ |
| 編輯老師個人檔案 | ✗ | ✗ | ✓（自己的） |

### 4.3 頁面存取規則

系統會依據使用者的角色，自動決定可進入的頁面：

| 使用者狀態 | 嘗試存取的頁面 | 系統行為 |
|-----------|-------------|---------|
| 未登入 | 任何需登入的頁面 | 自動導向登入頁 |
| 家長帳號 | 老師端頁面或管理員頁面 | 自動導回家長首頁 |
| 老師帳號 | 家長端頁面或管理員頁面 | 自動導回老師首頁 |
| 管理員帳號 | 任何頁面 | 皆可存取 |

類似學校的門禁系統——各角色僅能進入其權限範圍內的區域，管理員則擁有全域存取權限。

---

## 5. 功能模組規格

> 以下依英文字母 A~K 為各功能模組編號。每個模組代表系統中一個獨立的功能區塊。

### 5.1 模組 A：登入與註冊

本模組為使用者進入系統的第一步。

#### 註冊流程

1. 使用者於註冊頁面選擇身份（家長或老師）
2. 填寫帳號、密碼、姓名、電話、電子信箱
3. 密碼經加密後方存入資料庫（不儲存明碼）
4. 若註冊身份為老師，系統將自動建立一筆空白的老師個人檔案，供後續填寫

#### 登入流程

1. 輸入帳號與密碼
2. 驗證通過後，系統簽發一張「通行證」（JWT Token）
3. 通行證預設有效期限為 60 分鐘，逾期須重新登入
4. 後續每次操作，前端皆自動攜帶此通行證，無需重複登入

#### 管理員帳號

管理員帳號無需註冊。系統首次啟動時，會自動讀取 `.env` 設定檔中的管理員帳密並寫入資料庫。

### 5.2 模組 B：訊息系統

本模組提供一對一的純文字即時訊息功能，概念上類似 LINE 的文字聊天，但不含貼圖、檔案傳送或已讀標記。

#### 設計原則

- 任意兩位使用者之間最多存在一個對話（不會重複建立）
- 僅支援純文字訊息
- 任何使用者皆可主動向其他使用者開啟對話

#### 功能清單

| 功能 | 說明 |
|------|------|
| 對話列表 | 依最新訊息時間排列，顯示對方姓名與最新訊息摘要 |
| 聊天頁面 | 依時間順序顯示雙方訊息，底部設有文字輸入區與送出按鈕 |
| 開啟新對話 | 於老師詳情頁點擊「傳送訊息」即可開啟對話；若雙方已有既存對話，則自動導向該對話 |

### 5.3 模組 C：搜尋老師與個人檔案

#### 搜尋頁面

**篩選條件**（可組合使用）

| 條件 | 操作方式 | 說明 |
|------|---------|------|
| 科目 | 下拉選單 | 例如選「數學」，僅顯示可教數學的老師 |
| 時薪範圍 | 填寫最低與最高金額 | 例如 500~800，僅顯示時薪落於此區間的老師 |
| 最低評分 | 填寫數字 | 例如填 4，僅顯示平均評分 4 分以上的老師 |
| 學校 | 文字輸入 | 例如輸入「台大」，以模糊比對找出學校名稱含「台大」的老師 |

**排序方式**（三選一）

- 評分最高優先
- 時薪最低優先
- 最新註冊優先

**老師卡片的顯示內容**

- **系統強制顯示**：老師姓名、平均評分、評價數量
- **由老師自行控制是否公開**：學校、科系、年級、時薪、可教科目

此頁面的運作方式類似 Airbnb 的搜尋功能——設定篩選條件後，結果以卡片列表呈現，每張卡片包含關鍵資訊。

#### 老師詳情頁

| 區塊 | 內容 |
|------|------|
| 自我介紹 | 完整的自介文字與教學經歷 |
| 評價 | 各維度平均分數的雷達圖（蜘蛛網圖），以及歷史評價列表 |
| 接案狀態 | 已接學生數 / 接案上限（例如「已接 3 位 / 上限 5 位」） |
| 可用時段 | 以行事曆形式呈現每週可用時段 |
| 操作按鈕 | 「傳送訊息」與「送出邀請」 |

#### 老師個人檔案編輯

| 類別 | 可編輯欄位 |
|------|----------|
| 基本資料 | 姓名、學校、科系、年級、自我介紹、教學經歷 |
| 教學設定 | 可教科目（各科可設定不同時薪）、最大接案學生數 |
| 時段設定 | 每週哪幾天的哪些時段有空 |
| 隱私設定 | 控制學校、科系、年級、時薪、科目等欄位是否對外公開 |

### 5.4 模組 D：媒合流程與合約

本模組是系統中最核心的部分。一段配對從「送出邀請」到「合作結束」，會經歷多個階段。

#### 配對生命週期

```
  [pending] -----> [cancelled]
  等待中    家長撤回   已撤回
    |
    +-- 老師拒絕 --> [rejected] 已拒絕
    |
    +-- 老師接受
          |
          +-- 有勾試教 --> [trial] --> 雙方滿意 --> [active]
          |                試教中      不滿意 ----> [rejected]
          |
          +-- 沒勾試教 --> [active]
                          正式上課
                            |
              [paused] <--> + <-- 暫停 / 恢復
              暫停中        |
                            +-- 任一方提出終止
                            |
                            v
                      [terminating]
                      等對方同意
                            |
                  +---------+---------+
                  |                   |
             對方同意            對方不同意
                  |                   |
                  v                   v
              [ended]           回到之前狀態
              已結束            繼續上課
                  |
             開放撰寫評價
             (7 天內可修改)
```

#### 狀態轉換規則（完整版）

| 目前狀態 | 操作者 | 執行動作 | 轉換至 |
|---------|--------|---------|-------|
| 等待中 pending | 家長 | 撤回邀請 | 已撤回 cancelled |
| 等待中 pending | 老師 | 拒絕邀請 | 已拒絕 rejected |
| 等待中 pending | 老師 | 接受邀請 | 試教 trial 或 正式 active（依是否勾選試教而定） |
| 試教 trial | 雙方皆確認 | 試教通過 | 正式 active |
| 試教 trial | 任一方 | 試教不滿意 | 已拒絕 rejected |
| 正式 active | 任一方 | 暫停 | 暫停 paused |
| 正式 active | 任一方 | 提出終止 | 等待終止確認 terminating |
| 暫停 paused | 任一方 | 恢復 | 正式 active |
| 暫停 paused | 任一方 | 提出終止 | 等待終止確認 terminating |
| 等待終止 terminating | 對方 | 同意終止 | 已結束 ended |
| 等待終止 terminating | 對方 | 不同意 | 回到提出終止前的狀態 |

#### 合約條款

配對進入正式階段時，須記錄以下合約內容：

| 欄位 | 說明 |
|------|------|
| 正式時薪 | 每小時費用 |
| 每週堂數 | 約定之每週上課次數 |
| 合約起始日 | 開始日期 |
| 合約結束日 | 結束日期（可留空，終止時再填入） |
| 違約金 | 提前終止之違約金金額 |
| 試教費 | 試教期間的單堂費用（通常低於正式時薪） |
| 試教次數 | 約定之試教次數 |
| 附加條款 | 其他雙方自訂之備註事項 |

#### 邀請附帶資訊

| 欄位 | 必填 | 說明 |
|------|:----:|------|
| 指定子女 | ✓ | 從已建立之子女清單中選取 |
| 科目 | ✓ | 從老師可教授之科目中選取 |
| 建議時薪 | ✓ | 家長提議之金額 |
| 建議每週堂數 | ✓ | 希望的每週上課次數 |
| 是否試教 | ✓ | 勾選後配對將先進入試教階段 |
| 留言 | 選填 | 向老師說明教學需求或期望 |

### 5.5 模組 E：上課日誌

每次上課結束後，老師可於系統中記錄一篇上課紀錄，包含教學內容、指派作業、學生表現等。家長可依老師設定的公開狀態查閱相關紀錄。

#### 日誌欄位

| 欄位 | 必填 | 說明 |
|------|:----:|------|
| 上課日期 | ✓ | 日期選擇 |
| 上課時數 | ✓ | 支援小數，例如 1.5 小時 |
| 內容摘要 | ✓ | 本次教學內容 |
| 指派作業 | 選填 | 課後作業內容 |
| 學生表現 | 選填 | 老師對學生當堂表現的觀察 |
| 下次預計進度 | 選填 | 下次上課的預計教學範圍 |
| 是否公開給家長 | ✓ | 預設為不公開，老師可自行決定是否讓家長看到 |

#### 權限規則

- 僅配對中的老師可新增與編輯上課日誌
- 家長僅能查看老師設為「公開」的日誌
- 家長首頁（Dashboard）會自動顯示所有子女最近的已公開日誌

#### 修改歷史

日誌送出後仍允許修改，但每次修改皆會自動留下紀錄，包含：被修改的欄位、修改前內容、修改後內容、修改時間。概念類似 Google Docs 的版本紀錄。

### 5.6 模組 F：考試紀錄

#### 紀錄欄位

| 欄位 | 必填 | 說明 |
|------|:----:|------|
| 考試日期 | ✓ | 日期選擇 |
| 科目 | ✓ | 從科目清單中選取 |
| 考試類型 | ✓ | 段考、模考、或隨堂考 |
| 分數 | ✓ | 數字 |
| 是否公開給家長 | ✓ | 同上課日誌 |

#### 權限規則

- 老師與家長皆可新增考試紀錄
- 老師新增之紀錄，依「是否公開」決定家長是否可見
- 家長自行新增之紀錄，一律設為公開

#### 進步幅度計算

進步幅度不另存於資料庫。前端取得同一學生同一科目的歷次考試分數後，計算相鄰兩次的分數差值。

> 範例：某學生數學段考 72 → 85 → 90，進步幅度依序為 +13、+5。

### 5.7 模組 G：三向評價系統

一般平台僅有「消費者評供應者」的單向評價。本系統則設計了三個方向的評價機制，於合作結束後分別進行：

1. 家長 → 評老師（教學品質如何？）
2. 老師 → 評學生（學習態度如何？）
3. 老師 → 評家長（配合度如何？）

#### 各方向的評分維度

**家長評老師**

| 評分項目 | 分數範圍 |
|---------|---------|
| 教學品質 | 1~5 分 |
| 準時度 | 1~5 分 |
| 學生進步程度 | 1~5 分 |
| 溝通態度 | 1~5 分 |
| 性格評價 | 文字描述 |
| 整體評論 | 文字描述 |

**老師評學生**

| 評分項目 | 分數範圍 |
|---------|---------|
| 學習態度 | 1~5 分 |
| 作業完成度 | 1~5 分 |
| 性格評價 | 文字描述 |
| 整體評論 | 文字描述 |

**老師評家長**

| 評分項目 | 分數範圍 |
|---------|---------|
| 配合度（準時、不臨時取消） | 1~5 分 |
| 溝通態度（聯絡便利、尊重程度） | 1~5 分 |
| 繳費準時度 | 1~5 分 |
| 性格評價 | 文字描述 |
| 整體評論 | 文字描述 |

#### 評價規則

| 規則 | 說明 |
|------|------|
| 觸發時機 | 配對狀態變為「已結束 ended」後方可撰寫 |
| 次數限制 | 每段配對之每個方向僅限撰寫一次 |
| 修改期限 | 送出後 **7 天內**可修改，逾期鎖定 |
| 鎖定機制 | 後端比對評價建立時間與目前時間，超過 7 天即拒絕修改 |

#### 評價呈現方式

- **老師詳情頁**：以雷達圖呈現四個維度的平均分數，下方列出歷史評價
- **配對詳情頁**：顯示該配對之所有方向評價

### 5.8 模組 H：首頁 Dashboard

Dashboard 為登入後的首頁，彙整顯示使用者最需關注的資訊，功能類似手機的通知中心。

#### 老師首頁

| 區塊 | 顯示內容 |
|------|---------|
| 摘要卡片 | 目前學生數 / 接案上限、本月收入金額、待處理邀請數量 |
| 待處理 | 尚待回覆的邀請清單 |
| 進行中 | 目前所有進行中的配對（正式上課、試教中、暫停中），可點擊進入詳情 |

#### 家長首頁

| 區塊 | 顯示內容 |
|------|---------|
| 子女列表 | 各子女姓名及目前配對狀態一覽 |
| 待回覆邀請 | 已送出但尚未獲得老師回覆的邀請 |
| 最近動態 | 所有子女最新的已公開上課日誌 |
| 最新成績 | 各子女最近的已公開考試成績 |

### 5.9 模組 I：統計報表

#### 老師收入統計

- 支援三種分群維度：**按月份** / **按學生** / **按科目**
- 計算公式：`上課時數 x 時薪` 之加總
- 畫面呈現：柱狀圖搭配數據表格
- 計算透過背景任務執行，不阻塞使用者畫面

#### 家長支出統計

- 與老師收入統計對稱，支援按月份 / 按子女 / 按科目分群
- 計算公式相同

#### 學生成績趨勢

- **折線圖**：X 軸為考試日期，Y 軸為分數，支援按科目篩選
- **表格**：列出歷次考試，各筆顯示與同科目上次考試之分數差值

### 5.10 模組 J：資料匯入匯出與假資料

#### 匯出

- 全部 13 張資料表皆支援匯出為 **CSV 檔案**（可用 Excel 開啟）
- 匯出操作透過背景任務執行，不阻塞畫面，完成後提供下載

#### 匯入

- 提供兩種模式：
  - **比對更新（upsert）**：依主鍵比對，存在則更新，不存在則新增
  - **完全覆蓋（overwrite）**：清空目標表後全量寫入（僅管理員可用）
- 同樣透過背景任務執行

#### 假資料生成器

展示時需要一定數量的資料，但逐筆手動輸入並不實際。因此系統內建假資料產生器，可一鍵自動生成具有合理樣貌的假資料——包含中文姓名、台灣大專院校名稱、合理的評分分布與評語等。

### 5.11 模組 K：管理員後台

管理員專用的控制台，一般使用者無法存取。

| 功能 | 說明 |
|------|------|
| 匯入/匯出 | 可選擇單張或全部資料表進行匯入或匯出 |
| 清空資料庫 | 刪除所有資料（保留管理員帳號與表結構），操作前有確認提示 |
| 使用者管理 | 查看所有帳號列表，支援搜尋 |
| 系統狀態 | 顯示統計數據：總帳號數、老師數、家長數、配對數等 |
| 假資料生成 | 觸發背景任務產生並匯入假資料，介面顯示執行進度 |

---

<!-- ============================================================ -->
<!-- 以下為技術規格區（第 6~13 節 -->
<!-- ============================================================ -->

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

### 10.1 團隊組成

| 成員 | 技術背景 | 角色定位 |
|------|---------|---------|
| **A（Tech Lead）** | 全端開發 | 系統架構設計與核心開發 |
| **B** | 基礎網頁知識 | 前端開發支援 |
| **C** | 基礎網頁知識 | 前端開發支援 + 系統測試 |
| **D** | 正在學習 Access | 資料庫建置 + 簡報製作 |
| **E** | 正在學習 Access | 資料庫建置 + 書面報告 |

### 10.2 各成員職責

| 成員 | 負責範圍 | 交付物 |
|------|---------|--------|
| **A** | 後端架構搭建（FastAPI、Repository、JWT 認證）、huey worker 建置、複雜前端頁面（媒合狀態機、評價雷達圖、統計圖表）、假資料生成器、程式碼審查與技術指導 | 後端完整原始碼、核心前端頁面、start.bat |
| **B** | 前端頁面開發：登入/註冊頁、家長 Dashboard、搜尋頁面、老師卡片元件、訊息系統 UI | 所負責之 Vue 頁面與元件 |
| **C** | 前端頁面開發：老師 Dashboard、老師個人檔案編輯頁、上課日誌表單/時間軸、考試紀錄頁面；系統整合測試 | 所負責之 Vue 頁面與元件、測試紀錄文件 |
| **D** | 於 MS Access 中建立 13 張資料表與關聯圖、設定欄位型態與限制條件；簡報製作與上台口頭報告 | Access 資料庫檔案（.accdb）、PowerPoint 簡報 |
| **E** | 協助 D 完成 Access 資料表建置（分工各負責約一半的表）；書面報告撰寫（系統說明、功能截圖、使用者操作手冊） | Access 資料庫檔案（.accdb）、書面報告文件 |
| **全體** | 展示前排練、Demo 情境腳本設計與演練 | Demo 流程表 |

### 10.3 協作方式與時程搭配

| 週次 | A（Tech Lead） | B、C（前端） | D、E（Access + 文件） |
|:----:|---------------|-------------|---------------------|
| **1** | 搭建後端骨架、Auth 模組、huey 初始化、前端專案初始化 | 熟悉 Vue 開發環境、跑通範例頁面、練習 Axios 呼叫 API | 在 Access 中建立 13 張資料表、設定關聯圖，交付 .accdb 檔案 |
| **2** | 開發核心 API（老師搜尋、學生 CRUD、媒合狀態機、訊息） | B：登入/註冊頁、搜尋頁、老師卡片；C：老師 Dashboard、個人檔案編輯頁 | 用 Admin 後台匯入假資料，驗證資料表結構是否正確；開始規劃簡報大綱 |
| **3** | 開發教學管理 API（日誌、考試）、Admin 後台 API | B：家長 Dashboard、訊息系統 UI；C：上課日誌表單/時間軸、考試紀錄頁 | 按 Demo 腳本操作系統並截圖；撰寫書面報告初稿 |
| **4** | 開發評價系統、統計報表、CSV 匯入匯出、假資料生成器 | B：配對詳情頁（邀請表單、合約表單）；C：評價表單、整合測試 | 完成簡報製作；完成書面報告（含功能截圖與操作手冊） |
| **5** | 全系統 bug 修復、UI 細節調整 | 協助修復前端 bug、最終 UI 微調 | 全體排練展示流程、準備備用測試情境 |

### 10.4 B、C 組員的前端開發指引

B 和 C 負責的頁面不涉及後端邏輯，只需完成以下工作：

1. **畫面排版**：依照設計稿（或口頭討論的樣式）用 Vue 元件搭出頁面
2. **呼叫 API**：使用 `src/api/` 目錄下已封裝好的函式取得資料（A 會先寫好）
3. **資料綁定**：把 API 回傳的資料顯示到畫面上
4. **表單送出**：把使用者填寫的內容透過 API 送到後端

> A 會負責建立好前端專案結構、API 封裝層、路由設定、以及 Pinia store，讓 B 和 C 可以專注在「把頁面畫出來、把資料接上去」。

### 10.5 D、E 組員的 Access 建置指引

D 和 E 負責的工作不需要寫程式，但需要在 Access 裡精確地建好資料表：

1. **對照第 6 節的欄位規格表**，在 Access 的設計檢視中逐一建立欄位、設定資料型態和限制
2. **建立資料表之間的關聯**（在 Access 的「資料庫關聯圖」工具中拉線）
3. **建議分工**：D 負責 Users、Tutors、Students、Subjects、Tutor_Subjects、Tutor_Availability、Conversations（7 張）；E 負責 Messages、Matches、Sessions、Session_Edit_Logs、Exams、Reviews（6 張）
4. **完成後交給 A 驗證**——A 會用 pyodbc 連上去跑測試，確認欄位名稱和型態都正確

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
