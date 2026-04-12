# TMRP DDD 架構重構施工說明書

> **文件版本**：v1.0  
> **建立日期**：2026-04-12  
> **適用對象**：TMRP 後端 (`tutor-platform-api`)  
> **前端不受影響**：所有 API endpoint 路徑與 request/response 格式維持不變

---

## 目錄

1. [現狀分析與問題](#1-現狀分析與問題)
2. [DDD 核心概念速查](#2-ddd-核心概念速查)
3. [Bounded Context 劃分](#3-bounded-context-劃分)
4. [目標目錄結構](#4-目標目錄結構)
5. [各 Context 詳細設計](#5-各-context-詳細設計)
6. [Shared Kernel 設計](#6-shared-kernel-設計)
7. [跨 Context 通訊機制](#7-跨-context-通訊機制)
8. [遷移步驟與施工順序](#8-遷移步驟與施工順序)
9. [檔案搬遷對照表](#9-檔案搬遷對照表)
10. [測試策略](#10-測試策略)
11. [風險與注意事項](#11-風險與注意事項)

---

## 1. 現狀分析與問題

### 1.1 現有架構

```
app/
├── routers/          # Controller 層（13 個檔案）
├── models/           # Pydantic DTO（10 個檔案）
├── repositories/     # 資料存取層（10 個檔案）
├── middleware/        # HTTP 中介層
├── tasks/            # 背景任務
├── utils/            # 工具函式
├── config.py
├── database.py
├── database_tx.py
├── dependencies.py
├── exceptions.py
├── init_db.py
└── main.py
```

### 1.2 核心問題

| 問題 | 現象 | 範例位置 |
|------|------|----------|
| **業務邏輯散落在 Router** | 狀態機轉換、權限判斷、驗證邏輯全部寫在 endpoint function 裡 | `routers/matches.py` (230 行，含完整狀態機) |
| **缺少 Domain Model** | 沒有代表業務概念的 Entity/Value Object，所有資料以 `dict` 傳遞 | Repository 回傳 `dict`，Router 直接操作 `dict` key |
| **跨領域耦合** | 一個 Router 直接 import 多個不相關的 Repository | `routers/matches.py` 同時使用 StudentRepo + TutorRepo + MatchRepo |
| **無法獨立測試業務規則** | 要測試「配對狀態轉換是否正確」必須啟動 FastAPI + 資料庫 | 現有 tests 全部是整合測試 |
| **models/ 只是 DTO** | Pydantic Model 只做 HTTP 欄位驗證，不包含任何業務行為 | `models/match.py` 只有 2 個 dataclass |

### 1.3 什麼不是問題（不需要改）

- **前端架構**：Vue 3 + Pinia 已經很好，不在本次重構範圍
- **資料庫 Schema**：13 張表的設計合理，不需要改 DDL
- **Middleware / Config / Utils**：這些是基礎設施，與架構分層無關
- **API 路徑與格式**：所有 `/api/*` endpoint 保持不變，前端零修改

---

## 2. DDD 核心概念速查

> 這一節是給團隊成員的名詞解釋，已經懂的可以跳過。

### 2.1 戰略設計（Strategic Design）

| 概念 | 白話解釋 | TMRP 對應 |
|------|---------|-----------|
| **Bounded Context (BC)** | 一個獨立的業務領域，有自己的語言和邊界 | 「配對」和「評價」是兩個不同的 BC |
| **Ubiquitous Language** | 每個 BC 內統一使用的業務術語 | 在配對 BC 裡 `status` 是配對狀態，在評價 BC 裡 `status` 可能是鎖定狀態 |
| **Shared Kernel** | 多個 BC 共用的基礎型別 | `UserId`、`SubjectId`、`Subject` 清單 |
| **Context Map** | BC 之間的關係圖 | 教學 BC 依賴配對 BC 的 match_id |

### 2.2 戰術設計（Tactical Design）

| 概念 | 白話解釋 | TMRP 對應 |
|------|---------|-----------|
| **Entity** | 有唯一 ID 的業務物件，身份不因屬性改變而改變 | `Match`（即使狀態改了，它還是同一個配對） |
| **Value Object** | 無 ID、以值定義的不可變物件 | `Rating(1~5)`、`AvailabilitySlot(週三 14:00-16:00)` |
| **Aggregate Root (AR)** | 一組相關 Entity/VO 的「入口」，外部只能透過 AR 操作 | `Match` 是配對 Aggregate 的 Root |
| **Domain Service** | 不屬於任何單一 Entity 的業務邏輯 | 「驗證此老師是否教此科目」涉及 Tutor + Subject 兩個 Entity |
| **Port (介面)** | Domain 層定義的抽象介面，說「我需要什麼能力」 | `IMatchRepository`：「我需要能存取配對資料」 |
| **Adapter (實作)** | Infrastructure 層實作 Port 的具體類別 | `PostgresMatchRepository`：「我用 PostgreSQL 實作」 |
| **Application Service** | 協調 Domain 物件完成一個完整的 Use Case | `CreateMatchUseCase`：驗證 → 檢查重複 → 建立配對 |

### 2.3 依賴方向規則

```
API Layer (Router)
    ↓ 呼叫
Application Layer (Use Case / App Service)
    ↓ 呼叫
Domain Layer (Entity, VO, Domain Service, Port 介面)
    ↑ 實作（依賴反轉）
Infrastructure Layer (PostgreSQL Adapter, JWT 工具)
```

**核心原則**：Domain Layer 不 import 任何外部套件（不 import FastAPI、不 import psycopg2）。  
它是「純 Python」——只有 dataclass、enum、ABC、自定義 exception。

---

## 3. Bounded Context 劃分

### 3.1 Context Map

```
┌─────────────────────────────────────────────────────────┐
│                    Shared Kernel                         │
│         UserId, SubjectId, Subject 清單, 例外基底         │
└───────┬───────┬──────────┬──────────┬──────────┬────────┘
        │       │          │          │          │
   ┌────▼──┐ ┌─▼────┐ ┌──▼───┐ ┌───▼──┐ ┌────▼────┐
   │Identity│ │Catalog│ │Match │ │Review│ │Messaging│
   │身分認證│ │家教目錄│ │配對媒合│ │ 評價 │ │即時通訊 │
   └────────┘ └──┬────┘ └──┬───┘ └──┬───┘ └─────────┘
                 │     ┌───▼───┐    │
                 │     │Teaching│    │
                 │     │教學紀錄│    │
                 │     └───────┘    │
                 │                  │
              ┌──▼──────────────────▼──┐
              │      Analytics         │
              │    統計分析 (唯讀)      │
              └──────────┬─────────────┘
                         │
              ┌──────────▼─────────────┐
              │        Admin           │
              │  系統管理 (基礎設施)     │
              └────────────────────────┘
```

### 3.2 各 BC 職責與邊界

| BC | 核心職責 | 擁有的資料表 | 複雜度 |
|----|---------|-------------|--------|
| **Identity** | 註冊、登入、JWT、角色管理 | `users` | 低 |
| **Catalog** | 家教檔案、科目、時段、學生管理、搜尋 | `tutors`, `tutor_subjects`, `tutor_availability`, `students`, `subjects` | 中 |
| **Matching** | 配對生命週期（狀態機）、合約條款 | `matches` | **高**（核心域） |
| **Teaching** | 上課日誌、考試紀錄、編輯稽核 | `sessions`, `session_edit_logs`, `exams` | 中 |
| **Review** | 三向評價、評分、時間鎖 | `reviews` | 中 |
| **Messaging** | 對話建立、訊息收發 | `conversations`, `messages` | 低 |
| **Analytics** | 收入/支出/成績統計（唯讀查詢） | 無（跨表 JOIN 查詢） | 低 |
| **Admin** | 匯入匯出、重置、系統狀態 | 無（操作所有表） | 低（基礎設施） |

### 3.3 為什麼這樣劃分？

**Matching 是核心域（Core Domain）**：
- 狀態機有 8 種狀態、11 種轉換、角色權限矩陣——這是系統最複雜的業務規則
- 幾乎所有其他 BC 都依賴 `match_id`
- 配對的成立/終止會影響教學、評價、統計

**Catalog 獨立於 Matching**：
- 「家教檔案」和「配對」是不同的業務概念
- 家教可以存在但沒有任何配對
- 搜尋家教時不需要知道配對狀態

**Teaching 依賴 Matching**：
- Session/Exam 必須在 active match 下才能建立
- 但「上課紀錄」本身的 CRUD 和「配對狀態轉換」是獨立的業務邏輯

**Analytics 是 Query Side**：
- 只做跨表 JOIN 聚合，不修改任何資料
- 不需要 Domain Entity，直接 Repository → DTO 即可

---

## 4. 目標目錄結構

```
app/
│
├── shared/                              # ── Shared Kernel ──
│   ├── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── types.py                     # UserId, TutorId, MatchId 等型別別名
│   │   └── exceptions.py               # DomainException 基底類別
│   └── infrastructure/
│       ├── __init__.py
│       ├── config.py                    # Settings (從 app/config.py 搬入)
│       ├── database.py                  # 連線池 (從 app/database.py 搬入)
│       ├── database_tx.py              # 交易管理器 (從 app/database_tx.py 搬入)
│       ├── base_repository.py           # BaseRepository (從 repositories/base.py 搬入)
│       └── security.py                  # JWT + bcrypt (從 utils/security.py 搬入)
│
├── identity/                            # ── BC: 身分認證 ──
│   ├── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── entities.py                  # User entity
│   │   ├── services.py                  # AuthService (註冊/登入/token 邏輯)
│   │   ├── ports.py                     # IUserRepository (ABC)
│   │   └── exceptions.py               # DuplicateUsernameError 等
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   └── postgres_user_repo.py        # PostgreSQL 實作 IUserRepository
│   └── api/
│       ├── __init__.py
│       ├── router.py                    # auth 路由
│       ├── schemas.py                   # RegisterRequest, LoginRequest 等 DTO
│       └── dependencies.py              # get_current_user, require_role
│
├── catalog/                             # ── BC: 家教目錄 ──
│   ├── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── entities.py                  # Tutor, Student, Subject entities
│   │   ├── value_objects.py             # AvailabilitySlot, SubjectRate, Visibility
│   │   ├── services.py                  # TutorService, StudentService
│   │   ├── ports.py                     # ITutorRepository, IStudentRepository
│   │   └── exceptions.py               # TutorNotFoundError 等
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── postgres_tutor_repo.py
│   │   └── postgres_student_repo.py
│   └── api/
│       ├── __init__.py
│       ├── tutor_router.py
│       ├── student_router.py
│       ├── subject_router.py
│       └── schemas.py                   # TutorProfileUpdate, SubjectItem 等 DTO
│
├── matching/                            # ── BC: 配對媒合（核心域）──
│   ├── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── entities.py                  # Match (Aggregate Root)
│   │   ├── value_objects.py             # MatchStatus, Contract, StatusTransition
│   │   ├── state_machine.py             # MatchStateMachine (純邏輯，無 DB)
│   │   ├── services.py                  # MatchDomainService
│   │   ├── ports.py                     # IMatchRepository, ICatalogQuery
│   │   └── exceptions.py               # InvalidTransitionError, CapacityExceededError 等
│   ├── application/
│   │   ├── __init__.py
│   │   └── match_app_service.py         # CreateMatch, UpdateStatus 等 Use Case
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   └── postgres_match_repo.py
│   └── api/
│       ├── __init__.py
│       ├── router.py
│       └── schemas.py                   # MatchCreate, MatchStatusUpdate DTO
│
├── teaching/                            # ── BC: 教學紀錄 ──
│   ├── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── entities.py                  # Session, Exam entities
│   │   ├── value_objects.py             # EditLog
│   │   ├── services.py                  # SessionService, ExamService
│   │   ├── ports.py                     # ISessionRepository, IExamRepository
│   │   └── exceptions.py
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── postgres_session_repo.py
│   │   └── postgres_exam_repo.py
│   └── api/
│       ├── __init__.py
│       ├── session_router.py
│       ├── exam_router.py
│       └── schemas.py
│
├── review/                              # ── BC: 評價系統 ──
│   ├── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── entities.py                  # Review (Aggregate Root)
│   │   ├── value_objects.py             # ReviewType, Rating, LockWindow
│   │   ├── services.py                  # ReviewDomainService
│   │   ├── ports.py                     # IReviewRepository
│   │   └── exceptions.py               # ReviewLockedError 等
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   └── postgres_review_repo.py
│   └── api/
│       ├── __init__.py
│       ├── router.py
│       └── schemas.py
│
├── messaging/                           # ── BC: 即時通訊 ──
│   ├── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── entities.py                  # Conversation (AR), Message
│   │   ├── services.py                  # MessagingService
│   │   ├── ports.py                     # IMessageRepository
│   │   └── exceptions.py
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   └── postgres_message_repo.py
│   └── api/
│       ├── __init__.py
│       ├── router.py
│       └── schemas.py
│
├── analytics/                           # ── 統計分析（Query Side，輕量設計）──
│   ├── __init__.py
│   ├── query_service.py                 # StatsQueryService（直接查詢，無 Domain）
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   └── postgres_stats_repo.py
│   └── api/
│       ├── __init__.py
│       ├── router.py
│       └── schemas.py
│
├── admin/                               # ── 系統管理（基礎設施，輕量設計）──
│   ├── __init__.py
│   ├── services.py                      # AdminService
│   └── api/
│       ├── __init__.py
│       └── router.py
│
├── middleware/                          # ── 不變 ──
│   ├── __init__.py
│   ├── access_log.py
│   ├── rate_limit.py
│   ├── request_id.py
│   └── security_headers.py
│
├── tasks/                               # ── 背景任務（不變）──
│   ├── __init__.py
│   ├── import_export.py
│   ├── scheduled.py
│   ├── seed_tasks.py
│   └── stats_tasks.py
│
├── init_db.py                           # ── 不變 ──
├── worker.py                            # ── 不變 ──
└── main.py                              # ── 修改：改掛各 BC 的 router ──
```

### 4.1 檔案數量比較

| | 舊架構 | DDD 架構 |
|--|--------|---------|
| 目錄數 | 6 個 flat 目錄 | 8 個 BC + shared（每個 BC 3 層） |
| Python 檔案數 | ~35 | ~65 |
| 每個檔案平均行數 | ~100-230 行 | ~40-80 行 |

檔案數增加了，但每個檔案的職責更單一、行數更少、更容易理解。

---

## 5. 各 Context 詳細設計

### 5.1 Matching（核心域）— 最重要，設計最完整

這是系統最複雜的部分。以下是完整的 Domain Layer 設計：

#### 5.1.1 Value Objects (`matching/domain/value_objects.py`)

```python
from dataclasses import dataclass
from enum import Enum


class MatchStatus(str, Enum):
    """配對狀態，對應資料庫 matches.status 欄位"""
    PENDING = "pending"
    TRIAL = "trial"
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    TERMINATING = "terminating"
    ENDED = "ended"

    @property
    def label(self) -> str:
        return _STATUS_LABELS[self]

    @property
    def is_terminal(self) -> bool:
        return self in (self.CANCELLED, self.REJECTED, self.ENDED)


_STATUS_LABELS = {
    MatchStatus.PENDING: "等待中",
    MatchStatus.TRIAL: "試教中",
    MatchStatus.ACTIVE: "進行中",
    MatchStatus.PAUSED: "已暫停",
    MatchStatus.CANCELLED: "已取消",
    MatchStatus.REJECTED: "已拒絕",
    MatchStatus.TERMINATING: "等待終止確認",
    MatchStatus.ENDED: "已結束",
}


class Action(str, Enum):
    """使用者可執行的操作"""
    CANCEL = "cancel"
    REJECT = "reject"
    ACCEPT = "accept"
    CONFIRM_TRIAL = "confirm_trial"
    REJECT_TRIAL = "reject_trial"
    PAUSE = "pause"
    RESUME = "resume"
    TERMINATE = "terminate"
    AGREE_TERMINATE = "agree_terminate"
    DISAGREE_TERMINATE = "disagree_terminate"


class AllowedActor(str, Enum):
    """誰可以執行此操作"""
    PARENT = "parent"
    TUTOR = "tutor"
    EITHER = "either"
    OTHER_PARTY = "other_party"


@dataclass(frozen=True)
class Contract:
    """配對合約條款（Value Object，不可變）"""
    hourly_rate: float
    sessions_per_week: int
    want_trial: bool
    invite_message: str | None = None
```

#### 5.1.2 State Machine (`matching/domain/state_machine.py`)

```python
"""
配對狀態機 — 純邏輯，不依賴任何框架或資料庫。
可以單獨用 pytest 測試所有狀態轉換路徑。
"""
from dataclasses import dataclass

from .exceptions import InvalidTransitionError, PermissionDeniedError
from .value_objects import Action, AllowedActor, MatchStatus


@dataclass(frozen=True)
class Transition:
    new_status: MatchStatus | None   # None = 需要特殊處理
    allowed_actor: AllowedActor


# 狀態轉換表
TRANSITIONS: dict[tuple[MatchStatus, Action], Transition] = {
    (MatchStatus.PENDING, Action.CANCEL):
        Transition(MatchStatus.CANCELLED, AllowedActor.PARENT),
    (MatchStatus.PENDING, Action.REJECT):
        Transition(MatchStatus.REJECTED, AllowedActor.TUTOR),
    (MatchStatus.PENDING, Action.ACCEPT):
        Transition(None, AllowedActor.TUTOR),  # trial or active
    (MatchStatus.TRIAL, Action.CONFIRM_TRIAL):
        Transition(MatchStatus.ACTIVE, AllowedActor.EITHER),
    (MatchStatus.TRIAL, Action.REJECT_TRIAL):
        Transition(MatchStatus.REJECTED, AllowedActor.EITHER),
    (MatchStatus.ACTIVE, Action.PAUSE):
        Transition(MatchStatus.PAUSED, AllowedActor.EITHER),
    (MatchStatus.ACTIVE, Action.TERMINATE):
        Transition(MatchStatus.TERMINATING, AllowedActor.EITHER),
    (MatchStatus.PAUSED, Action.RESUME):
        Transition(MatchStatus.ACTIVE, AllowedActor.EITHER),
    (MatchStatus.PAUSED, Action.TERMINATE):
        Transition(MatchStatus.TERMINATING, AllowedActor.EITHER),
    (MatchStatus.TERMINATING, Action.AGREE_TERMINATE):
        Transition(MatchStatus.ENDED, AllowedActor.OTHER_PARTY),
    (MatchStatus.TERMINATING, Action.DISAGREE_TERMINATE):
        Transition(None, AllowedActor.OTHER_PARTY),  # revert
}


def resolve_transition(
    current: MatchStatus,
    action: Action,
    *,
    actor_is_parent: bool,
    actor_is_tutor: bool,
    actor_is_admin: bool,
    actor_user_id: int,
    terminated_by: int | None,
    want_trial: bool,
) -> MatchStatus:
    """
    給定目前狀態和操作，回傳新狀態。

    如果轉換不合法或角色不符，拋出 Domain Exception。
    此函式是純函式 — 不碰 DB、不碰框架。
    """
    transition = TRANSITIONS.get((current, action))
    if transition is None:
        raise InvalidTransitionError(
            f"無法在「{current.label}」狀態執行「{action.value}」操作"
        )

    # 權限檢查
    _check_permission(
        transition.allowed_actor,
        actor_is_parent=actor_is_parent,
        actor_is_tutor=actor_is_tutor,
        actor_is_admin=actor_is_admin,
        actor_user_id=actor_user_id,
        terminated_by=terminated_by,
    )

    # 特殊轉換
    if action == Action.ACCEPT:
        return MatchStatus.TRIAL if want_trial else MatchStatus.ACTIVE

    if action == Action.DISAGREE_TERMINATE:
        # 回復到 terminating 之前的狀態由呼叫方從 termination_reason 解析
        # 這裡回傳 None 作為 sentinel，由 Application Service 處理
        return None  # type: ignore

    return transition.new_status


def _check_permission(
    allowed: AllowedActor,
    *,
    actor_is_parent: bool,
    actor_is_tutor: bool,
    actor_is_admin: bool,
    actor_user_id: int,
    terminated_by: int | None,
) -> None:
    if actor_is_admin and allowed != AllowedActor.OTHER_PARTY:
        return  # admin 可跳過一般角色限制

    match allowed:
        case AllowedActor.PARENT:
            if not actor_is_parent:
                raise PermissionDeniedError("只有家長可以執行此操作")
        case AllowedActor.TUTOR:
            if not actor_is_tutor:
                raise PermissionDeniedError("只有老師可以執行此操作")
        case AllowedActor.EITHER:
            if not actor_is_parent and not actor_is_tutor and not actor_is_admin:
                raise PermissionDeniedError("無權操作此配對")
        case AllowedActor.OTHER_PARTY:
            if terminated_by == actor_user_id:
                raise PermissionDeniedError("需要由對方確認此操作")
```

#### 5.1.3 Match Entity (`matching/domain/entities.py`)

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .value_objects import Contract, MatchStatus


@dataclass
class Match:
    """
    Match Aggregate Root

    代表一筆「家教 ↔ 學生」的配對關係。
    所有狀態變更必須透過此物件的方法進行。
    """
    match_id: int
    tutor_id: int
    student_id: int
    subject_id: int
    status: MatchStatus
    contract: Contract
    terminated_by: int | None = None
    termination_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # 關聯資料（由 Repository 組裝，Domain 邏輯不依賴）
    subject_name: str | None = None
    student_name: str | None = None
    parent_user_id: int | None = None
    tutor_user_id: int | None = None
    tutor_display_name: str | None = None

    @property
    def status_label(self) -> str:
        return self.status.label

    @property
    def parsed_termination_reason(self) -> str | None:
        """去掉 'previous_status|' 前綴，回傳使用者看到的原因"""
        if not self.termination_reason:
            return None
        if "|" in self.termination_reason:
            return self.termination_reason.split("|", 1)[1]
        return self.termination_reason

    @property
    def previous_status_before_terminating(self) -> str:
        """從 termination_reason 解析終止前的狀態"""
        raw = self.termination_reason or ""
        if "|" in raw:
            prev = raw.split("|")[0]
            if prev in ("active", "paused"):
                return prev
        return "active"  # fallback

    def is_participant(self, user_id: int) -> bool:
        return user_id == self.parent_user_id or user_id == self.tutor_user_id
```

#### 5.1.4 Port 介面 (`matching/domain/ports.py`)

```python
from abc import ABC, abstractmethod

from .entities import Match


class IMatchRepository(ABC):
    """配對資料存取介面 — Domain 只知道這個介面，不知道 PostgreSQL"""

    @abstractmethod
    def find_by_id(self, match_id: int) -> Match | None: ...

    @abstractmethod
    def find_by_tutor_user_id(self, user_id: int) -> list[dict]: ...

    @abstractmethod
    def find_by_parent_user_id(self, user_id: int) -> list[dict]: ...

    @abstractmethod
    def find_all(self) -> list[dict]: ...

    @abstractmethod
    def create(self, tutor_id: int, student_id: int, subject_id: int,
               hourly_rate: float, sessions_per_week: int,
               want_trial: bool, invite_message: str | None) -> int: ...

    @abstractmethod
    def update_status(self, match_id: int, new_status: str) -> None: ...

    @abstractmethod
    def set_terminating(self, match_id: int, user_id: int,
                        reason: str, previous_status: str) -> None: ...

    @abstractmethod
    def clear_termination(self, match_id: int, revert_status: str) -> None: ...

    @abstractmethod
    def check_duplicate_active(self, tutor_id: int,
                               student_id: int, subject_id: int) -> bool: ...


class ICatalogQuery(ABC):
    """配對 BC 對 Catalog BC 的查詢介面（跨 Context 查詢）"""

    @abstractmethod
    def get_student_owner(self, student_id: int) -> int | None:
        """回傳 student 的 parent_user_id，不存在回傳 None"""
        ...

    @abstractmethod
    def tutor_exists(self, tutor_id: int) -> bool: ...

    @abstractmethod
    def tutor_teaches_subject(self, tutor_id: int, subject_id: int) -> bool: ...

    @abstractmethod
    def get_active_student_count(self, tutor_id: int) -> int: ...

    @abstractmethod
    def get_max_students(self, tutor_id: int) -> int: ...
```

#### 5.1.5 Application Service (`matching/application/match_app_service.py`)

```python
"""
Application Service — 協調 Domain 物件完成 Use Case

職責：
1. 從 Port 取得資料
2. 呼叫 Domain 邏輯（state_machine, entity）
3. 管理交易邊界
4. 回傳結果給 API 層
"""
from app.matching.domain import state_machine
from app.matching.domain.exceptions import (
    CapacityExceededError,
    DuplicateMatchError,
    InvalidTransitionError,
    MatchNotFoundError,
    PermissionDeniedError,
    StudentNotOwnedError,
    SubjectNotTaughtError,
    TutorNotFoundError,
)
from app.matching.domain.ports import ICatalogQuery, IMatchRepository
from app.matching.domain.value_objects import Action, MatchStatus
from app.shared.infrastructure.database_tx import transaction


class MatchAppService:
    def __init__(self, match_repo: IMatchRepository, catalog: ICatalogQuery, conn):
        self._match_repo = match_repo
        self._catalog = catalog
        self._conn = conn

    def create_match(
        self, *, user_id: int, tutor_id: int, student_id: int,
        subject_id: int, hourly_rate: float, sessions_per_week: int,
        want_trial: bool, invite_message: str | None,
    ) -> int:
        # 驗證學生歸屬
        owner = self._catalog.get_student_owner(student_id)
        if owner != user_id:
            raise StudentNotOwnedError()

        # 驗證老師存在
        if not self._catalog.tutor_exists(tutor_id):
            raise TutorNotFoundError()

        # 驗證老師教此科目
        if not self._catalog.tutor_teaches_subject(tutor_id, subject_id):
            raise SubjectNotTaughtError()

        # 交易內：重複檢查 + 容量檢查 + INSERT
        with transaction(self._conn):
            if self._match_repo.check_duplicate_active(tutor_id, student_id, subject_id):
                raise DuplicateMatchError()

            active = self._catalog.get_active_student_count(tutor_id)
            max_s = self._catalog.get_max_students(tutor_id)
            if active >= max_s:
                raise CapacityExceededError()

            return self._match_repo.create(
                tutor_id=tutor_id, student_id=student_id,
                subject_id=subject_id, hourly_rate=hourly_rate,
                sessions_per_week=sessions_per_week,
                want_trial=want_trial, invite_message=invite_message,
            )

    def list_matches(self, *, user_id: int, role: str) -> list[dict]:
        if role == "tutor":
            matches = self._match_repo.find_by_tutor_user_id(user_id)
        elif role == "admin":
            matches = self._match_repo.find_all()
        else:
            matches = self._match_repo.find_by_parent_user_id(user_id)

        for m in matches:
            m["status_label"] = MatchStatus(m["status"]).label
        return matches

    def get_detail(self, *, match_id: int, user_id: int, is_admin: bool) -> dict:
        match = self._match_repo.find_by_id(match_id)
        if match is None:
            raise MatchNotFoundError()

        is_parent = match.parent_user_id == user_id
        is_tutor = match.tutor_user_id == user_id
        if not is_parent and not is_tutor and not is_admin:
            raise PermissionDeniedError("無權查看此配對")

        return {
            "match": match,
            "is_parent": is_parent,
            "is_tutor": is_tutor,
        }

    def update_status(
        self, *, match_id: int, action_str: str, reason: str | None,
        user_id: int, is_admin: bool,
    ) -> dict:
        match = self._match_repo.find_by_id(match_id)
        if match is None:
            raise MatchNotFoundError()

        is_parent = match.parent_user_id == user_id
        is_tutor = match.tutor_user_id == user_id
        if not is_parent and not is_tutor and not is_admin:
            raise PermissionDeniedError("無權操作此配對")

        action = Action(action_str)

        # Domain 純邏輯：計算新狀態
        new_status = state_machine.resolve_transition(
            current=match.status,
            action=action,
            actor_is_parent=is_parent,
            actor_is_tutor=is_tutor,
            actor_is_admin=is_admin,
            actor_user_id=user_id,
            terminated_by=match.terminated_by,
            want_trial=match.contract.want_trial,
        )

        # 持久化
        if action == Action.TERMINATE:
            if not reason:
                raise InvalidTransitionError("終止配對需要提供原因")
            self._match_repo.set_terminating(
                match_id, user_id, reason, match.status.value
            )
            new_status = MatchStatus.TERMINATING

        elif action == Action.DISAGREE_TERMINATE:
            with transaction(self._conn):
                fresh = self._match_repo.find_by_id(match_id)
                if not fresh or fresh.status != MatchStatus.TERMINATING:
                    raise InvalidTransitionError("配對狀態已變更，請重新整理頁面")
                prev = fresh.previous_status_before_terminating
                self._match_repo.clear_termination(match_id, prev)
                new_status = MatchStatus(prev)
        else:
            self._match_repo.update_status(match_id, new_status.value)

        return {
            "match_id": match_id,
            "new_status": new_status.value,
            "status_label": new_status.label,
        }
```

#### 5.1.6 Router (`matching/api/router.py`)

```python
"""
API Layer — 薄薄的轉接層，只做 HTTP ↔ Application Service 的橋接
"""
from fastapi import APIRouter, Depends

from app.identity.api.dependencies import get_current_user, is_admin, require_role
from app.matching.api.schemas import MatchCreate, MatchStatusUpdate
from app.matching.application.match_app_service import MatchAppService
from app.shared.domain.exceptions import DomainException
from app.shared.infrastructure.database import get_db

# ... 工廠函式建立 MatchAppService（注入 repo + conn）

router = APIRouter(prefix="/api/matches", tags=["matches"])


@router.post("", summary="建立配對邀請")
def create_match(
    body: MatchCreate,
    user=Depends(require_role("parent")),
    conn=Depends(get_db),
):
    service = _build_service(conn)
    match_id = service.create_match(
        user_id=int(user["sub"]),
        tutor_id=body.tutor_id,
        student_id=body.student_id,
        subject_id=body.subject_id,
        hourly_rate=body.hourly_rate,
        sessions_per_week=body.sessions_per_week,
        want_trial=body.want_trial,
        invite_message=body.invite_message,
    )
    return {"success": True, "data": {"match_id": match_id}, "message": "媒合邀請已送出"}
```

> **對比**：原本 `routers/matches.py` 的 `create_match` 有 40 行業務邏輯。
> 重構後 Router 只有 ~15 行，純粹做「拆參數 → 呼叫 service → 包回應」。

---

### 5.2 Identity（身分認證）

#### Domain 設計重點

```python
# identity/domain/entities.py
@dataclass
class User:
    user_id: int
    username: str
    password_hash: str
    role: str           # "parent" | "tutor" | "admin"
    display_name: str
    phone: str | None = None
    email: str | None = None

# identity/domain/services.py
class AuthService:
    """純業務邏輯：不碰 DB，只碰 Entity 和 Port"""
    def __init__(self, user_repo: IUserRepository):
        self._repo = user_repo

    def register(self, username, password, display_name, role, phone, email) -> int:
        # 密碼雜湊、重複檢查、建立 user + tutor record
        ...

    def login(self, username, password) -> User:
        # 查詢 user、驗證密碼
        ...
```

#### 搬遷來源

| 新位置 | 舊位置 |
|-------|--------|
| `identity/domain/services.py` | `routers/auth.py` 裡的業務邏輯 |
| `identity/infrastructure/postgres_user_repo.py` | `repositories/auth_repo.py` |
| `identity/api/router.py` | `routers/auth.py` 裡的 endpoint 定義 |
| `identity/api/schemas.py` | `models/auth.py` |
| `identity/api/dependencies.py` | `dependencies.py` |

---

### 5.3 Catalog（家教目錄）

#### Domain 設計重點

```python
# catalog/domain/value_objects.py
@dataclass(frozen=True)
class AvailabilitySlot:
    day_of_week: int      # 0-6
    start_time: str       # "HH:MM"
    end_time: str         # "HH:MM"

@dataclass(frozen=True)
class SubjectRate:
    subject_id: int
    subject_name: str
    hourly_rate: float

@dataclass(frozen=True)
class Visibility:
    show_university: bool = True
    show_department: bool = True
    show_grade_year: bool = True
    show_hourly_rate: bool = True
    show_subjects: bool = True

# catalog/domain/entities.py
@dataclass
class Tutor:
    tutor_id: int
    user_id: int
    university: str | None
    department: str | None
    grade_year: int | None
    self_intro: str | None
    teaching_experience: str | None
    max_students: int
    visibility: Visibility
    display_name: str | None = None

    def apply_privacy(self, data: dict) -> dict:
        """對非本人隱藏隱私欄位"""
        if not self.visibility.show_university:
            data.pop("university", None)
        # ... 其餘欄位同理
        return data

@dataclass
class Student:
    student_id: int
    parent_user_id: int
    name: str
    school: str | None = None
    grade: str | None = None
    target_school: str | None = None
```

#### 搬遷來源

| 新位置 | 舊位置 |
|-------|--------|
| `catalog/domain/services.py` | `routers/tutors.py` 裡的搜尋/隱私邏輯 |
| `catalog/infrastructure/postgres_tutor_repo.py` | `repositories/tutor_repo.py` |
| `catalog/infrastructure/postgres_student_repo.py` | `repositories/student_repo.py` |
| `catalog/api/tutor_router.py` | `routers/tutors.py` |
| `catalog/api/student_router.py` | `routers/students.py` |
| `catalog/api/subject_router.py` | `routers/subjects.py` |
| `catalog/api/schemas.py` | `models/tutor.py` + `models/student.py` |

---

### 5.4 Teaching（教學紀錄）

#### Domain 設計重點

```python
# teaching/domain/entities.py
@dataclass
class Session:
    session_id: int
    match_id: int
    session_date: datetime
    hours: float
    content_summary: str
    homework: str | None
    student_performance: str | None
    next_plan: str | None
    visible_to_parent: bool

    def compute_edit_diffs(self, updates: dict, old_data: dict) -> list[EditLog]:
        """比對新舊值，產生編輯紀錄（Domain 邏輯）"""
        diffs = []
        for field, new_val in updates.items():
            old_val = old_data.get(field)
            if str(new_val) != str(old_val):
                diffs.append(EditLog(
                    field_name=field,
                    old_value=str(old_val) if old_val is not None else None,
                    new_value=str(new_val),
                ))
        return diffs

# teaching/domain/value_objects.py
@dataclass(frozen=True)
class EditLog:
    field_name: str
    old_value: str | None
    new_value: str | None
```

#### 搬遷來源

| 新位置 | 舊位置 |
|-------|--------|
| `teaching/domain/services.py` | `routers/sessions.py` 裡的稽核邏輯 + `routers/exams.py` 裡的權限邏輯 |
| `teaching/infrastructure/postgres_session_repo.py` | `repositories/session_repo.py` |
| `teaching/infrastructure/postgres_exam_repo.py` | `repositories/exam_repo.py` |
| `teaching/api/session_router.py` | `routers/sessions.py` |
| `teaching/api/exam_router.py` | `routers/exams.py` |
| `teaching/api/schemas.py` | `models/session.py` + `models/exam.py` |

---

### 5.5 Review（評價系統）

#### Domain 設計重點

```python
# review/domain/value_objects.py
class ReviewType(str, Enum):
    PARENT_TO_TUTOR = "parent_to_tutor"
    TUTOR_TO_PARENT = "tutor_to_parent"
    TUTOR_TO_STUDENT = "tutor_to_student"

@dataclass(frozen=True)
class Rating:
    """1~5 分的評分，建構時自動驗證"""
    value: int
    def __post_init__(self):
        if not 1 <= self.value <= 5:
            raise ValueError(f"評分必須在 1-5 之間，收到 {self.value}")

# review/domain/entities.py
@dataclass
class Review:
    """Review Aggregate Root"""
    review_id: int
    match_id: int
    reviewer_user_id: int
    review_type: ReviewType
    rating_1: int
    rating_2: int
    rating_3: int | None
    rating_4: int | None
    personality_comment: str | None
    comment: str | None
    is_locked: bool
    created_at: datetime
    updated_at: datetime | None

    def is_editable(self, lock_days: int) -> bool:
        """檢查是否在可編輯的時間窗口內"""
        if self.is_locked:
            return False
        cutoff = self.created_at + timedelta(days=lock_days)
        return datetime.now(timezone.utc) < cutoff

    def validate_reviewer_role(self, user_role: str, user_id: int,
                                tutor_user_id: int, parent_user_id: int) -> None:
        """驗證此角色是否可以提交此類型的評價"""
        if self.review_type == ReviewType.PARENT_TO_TUTOR:
            if user_id != parent_user_id:
                raise PermissionError("只有家長可以評價老師")
        elif self.review_type in (ReviewType.TUTOR_TO_PARENT, ReviewType.TUTOR_TO_STUDENT):
            if user_id != tutor_user_id:
                raise PermissionError("只有老師可以評價家長/學生")
```

---

### 5.6 Messaging / Analytics / Admin

這三個 BC 的業務邏輯較簡單，採用**輕量 DDD**：

- **Messaging**：Entity (Conversation, Message) + Service + Port，無複雜 Domain 規則
- **Analytics**：純 Query Side，只有 `QueryService` + `StatsRepository`，不需要 Domain Layer
- **Admin**：基礎設施操作，保持現有結構，只搬位置

---

## 6. Shared Kernel 設計

### 6.1 共用型別 (`shared/domain/types.py`)

```python
"""
型別別名，讓程式碼語義更清楚。
使用 NewType 而非裸 int，IDE 可以提示型別錯用。
"""
from typing import NewType

UserId = NewType("UserId", int)
TutorId = NewType("TutorId", int)
StudentId = NewType("StudentId", int)
MatchId = NewType("MatchId", int)
SubjectId = NewType("SubjectId", int)
SessionId = NewType("SessionId", int)
ReviewId = NewType("ReviewId", int)
ConversationId = NewType("ConversationId", int)
```

### 6.2 共用例外 (`shared/domain/exceptions.py`)

```python
class DomainException(Exception):
    """所有 Domain 例外的基底"""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code

class NotFoundError(DomainException):
    def __init__(self, message: str = "資源不存在"):
        super().__init__(message, 404)

class PermissionDeniedError(DomainException):
    def __init__(self, message: str = "無權限執行此操作"):
        super().__init__(message, 403)

class ConflictError(DomainException):
    def __init__(self, message: str = "資源狀態衝突"):
        super().__init__(message, 409)
```

> 這取代了舊的 `app/exceptions.py`。原本的 `AppException` → `DomainException`、
> `NotFoundException` → `NotFoundError`、以此類推。
> `main.py` 的 exception handler 改為捕捉 `DomainException`。

### 6.3 基礎設施搬遷

| 新位置 | 舊位置 | 改動 |
|-------|--------|------|
| `shared/infrastructure/config.py` | `app/config.py` | 只改 import path |
| `shared/infrastructure/database.py` | `app/database.py` | 只改 import path |
| `shared/infrastructure/database_tx.py` | `app/database_tx.py` | 只改 import path |
| `shared/infrastructure/base_repository.py` | `repositories/base.py` | 只改 import path |
| `shared/infrastructure/security.py` | `utils/security.py` | 只改 import path |

---

## 7. 跨 Context 通訊機制

### 7.1 原則

BC 之間**不直接 import 對方的 Domain 物件**。通訊方式有兩種：

1. **Query Interface（查詢介面）**：A 的 Domain 定義一個 Port，B 的 Infrastructure 實作它
2. **Shared ID（共用識別碼）**：只共用 ID（如 `match_id: int`），不共用 Entity

### 7.2 跨 Context 依賴清單

```
Matching  ──查詢──→  Catalog     (需要驗證學生/老師/科目)
Teaching  ──查詢──→  Matching    (需要驗證 match 狀態)
Review    ──查詢──→  Matching    (需要驗證 match 參與者)
Analytics ──查詢──→  所有 BC     (跨表 JOIN，直接走 Repository)
Admin     ──操作──→  所有資料表  (基礎設施操作，不經過 Domain)
```

### 7.3 實作方式

以 Matching → Catalog 為例：

```python
# matching/domain/ports.py 定義介面
class ICatalogQuery(ABC):
    @abstractmethod
    def get_student_owner(self, student_id: int) -> int | None: ...

# catalog/infrastructure/catalog_query_adapter.py 實作
class CatalogQueryAdapter(ICatalogQuery):
    def __init__(self, conn):
        self._conn = conn

    def get_student_owner(self, student_id: int) -> int | None:
        cur = self._conn.cursor()
        cur.execute("SELECT parent_user_id FROM students WHERE student_id = %s", (student_id,))
        row = cur.fetchone()
        return row[0] if row else None
```

**依賴方向**：
- `matching/domain/` 只知道 `ICatalogQuery`（抽象）
- `catalog/infrastructure/` 實作它（具體）
- 組裝發生在 Router 或工廠函式中

---

## 8. 遷移步驟與施工順序

### 8.1 遷移原則

1. **逐步搬遷，不一次全改**：一次搬一個 BC，搬完確認 API 測試通過再搬下一個
2. **舊新共存**：過渡期間 `app/routers/` 和 `app/matching/api/` 可以同時存在
3. **API 不變**：每一步都確保 `GET /api/matches` 等 endpoint 回應格式不變
4. **先搬 Shared，再搬各 BC**

### 8.2 施工順序

```
Phase 0: 準備工作
    ↓
Phase 1: 建立 Shared Kernel
    ↓
Phase 2: 搬遷 Identity BC
    ↓
Phase 3: 搬遷 Catalog BC
    ↓
Phase 4: 搬遷 Matching BC（核心，最複雜）
    ↓
Phase 5: 搬遷 Teaching BC
    ↓
Phase 6: 搬遷 Review BC
    ↓
Phase 7: 搬遷 Messaging BC
    ↓
Phase 8: 搬遷 Analytics + Admin
    ↓
Phase 9: 清理舊檔案 + 最終驗證
```

---

### Phase 0: 準備工作

**目標**：確保有一個可信賴的回歸測試基準

- [ ] 確保所有現有 test 通過（`pytest tests/`）
- [ ] 手動跑一遍所有 API endpoint，記錄預期 response（或用 `httpx` 寫快照測試）
- [ ] 建立 `feature/ddd-migration` 分支

---

### Phase 1: 建立 Shared Kernel

**目標**：搬遷共用基礎設施，讓後續各 BC 可以 import

**步驟**：

1. 建立目錄結構：
   ```
   app/shared/__init__.py
   app/shared/domain/__init__.py
   app/shared/infrastructure/__init__.py
   ```

2. 搬遷檔案（只搬位置 + 更新 import）：
   - `app/config.py` → `app/shared/infrastructure/config.py`
   - `app/database.py` → `app/shared/infrastructure/database.py`
   - `app/database_tx.py` → `app/shared/infrastructure/database_tx.py`
   - `repositories/base.py` → `app/shared/infrastructure/base_repository.py`
   - `utils/security.py` → `app/shared/infrastructure/security.py`

3. 建立新檔案：
   - `app/shared/domain/types.py`（型別別名）
   - `app/shared/domain/exceptions.py`（DomainException 取代 AppException）

4. 在舊位置放 re-export shim（過渡用）：
   ```python
   # app/config.py（過渡用，最後 Phase 9 刪除）
   from app.shared.infrastructure.config import settings, Settings  # noqa: F401
   ```

5. **驗證**：跑 `pytest` + 手動測試，確認無 import 錯誤

---

### Phase 2: 搬遷 Identity BC

**目標**：auth 相關程式碼搬入 `app/identity/`

**步驟**：

1. 建立目錄結構：
   ```
   app/identity/{__init__, domain/, infrastructure/, api/}
   ```

2. **Domain Layer**：
   - 建立 `identity/domain/entities.py`（User dataclass）
   - 建立 `identity/domain/ports.py`（IUserRepository ABC）
   - 建立 `identity/domain/services.py`（AuthService：從 `routers/auth.py` 抽出註冊/登入/token 邏輯）
   - 建立 `identity/domain/exceptions.py`（DuplicateUsernameError, InvalidCredentialsError）

3. **Infrastructure Layer**：
   - 搬遷 `repositories/auth_repo.py` → `identity/infrastructure/postgres_user_repo.py`
   - 改為 implements IUserRepository

4. **API Layer**：
   - 搬遷 `models/auth.py` → `identity/api/schemas.py`
   - 搬遷 `dependencies.py` → `identity/api/dependencies.py`
   - 重寫 `routers/auth.py` → `identity/api/router.py`（薄 Router，呼叫 AuthService）

5. **main.py**：改為 `from app.identity.api.router import router as auth_router`

6. **驗證**：
   - `POST /api/auth/register` 註冊測試
   - `POST /api/auth/login` 登入測試
   - `POST /api/auth/refresh` token 更新
   - `GET /api/auth/me` 取得個人資訊

---

### Phase 3: 搬遷 Catalog BC

**步驟**：

1. 建立 `app/catalog/` 結構

2. **Domain**：
   - 建立 Tutor, Student, Subject entity
   - 建立 AvailabilitySlot, SubjectRate, Visibility value objects
   - 建立 ITutorRepository, IStudentRepository ports
   - 建立 TutorService（搜尋邏輯 + 隱私過濾）、StudentService

3. **Infrastructure**：
   - 搬遷 `repositories/tutor_repo.py` → `catalog/infrastructure/postgres_tutor_repo.py`
   - 搬遷 `repositories/student_repo.py` → `catalog/infrastructure/postgres_student_repo.py`
   - 建立 `CatalogQueryAdapter`（供 Matching BC 跨 Context 查詢）

4. **API**：
   - 搬遷 tutors/students/subjects 三個 router
   - 搬遷 `models/tutor.py` + `models/student.py` → `catalog/api/schemas.py`

5. **驗證**：搜尋家教、更新檔案、管理子女等功能

---

### Phase 4: 搬遷 Matching BC（核心）

**這是最大的施工項目，建議拆成子步驟**：

1. **4a**：建立 Domain Layer（entities, value_objects, state_machine, ports, exceptions）
2. **4b**：寫 state_machine 的單元測試（純邏輯，不需要 DB）
   ```python
   def test_pending_accept_with_trial():
       result = resolve_transition(
           current=MatchStatus.PENDING, action=Action.ACCEPT,
           actor_is_parent=False, actor_is_tutor=True, ...
           want_trial=True,
       )
       assert result == MatchStatus.TRIAL
   ```
3. **4c**：建立 Infrastructure（postgres_match_repo.py，implements IMatchRepository）
4. **4d**：建立 Application Service（match_app_service.py）
5. **4e**：建立 API Router（薄 Router）
6. **4f**：端對端驗證所有 match 相關 API

---

### Phase 5-7: Teaching / Review / Messaging

每個 BC 的步驟相同：
1. 建立 domain/（entities, services, ports）
2. 搬遷 infrastructure/（repo 加上 interface）
3. 搬遷 api/（router 瘦身 + schemas）
4. 驗證 API

---

### Phase 8: Analytics + Admin

- **Analytics**：輕量設計，query_service + repo + router
- **Admin**：保持原結構，只搬位置到 `app/admin/`

---

### Phase 9: 清理

1. 刪除 `app/routers/` 目錄（所有 router 已搬入各 BC）
2. 刪除 `app/models/` 目錄（所有 schema 已搬入各 BC）
3. 刪除 `app/repositories/` 目錄（所有 repo 已搬入各 BC）
4. 刪除 `app/dependencies.py`（已搬入 identity/api/）
5. 刪除 `app/exceptions.py`（已由 shared/domain/exceptions.py 取代）
6. 刪除 `app/utils/`（security 已搬入 shared/infrastructure/）
7. 刪除所有 re-export shim
8. 全面跑 `pytest` + 手動端對端測試

---

## 9. 檔案搬遷對照表

### 9.1 刪除（搬遷後的舊位置）

| 舊檔案 | 搬遷至 |
|--------|--------|
| `app/config.py` | `app/shared/infrastructure/config.py` |
| `app/database.py` | `app/shared/infrastructure/database.py` |
| `app/database_tx.py` | `app/shared/infrastructure/database_tx.py` |
| `app/dependencies.py` | `app/identity/api/dependencies.py` |
| `app/exceptions.py` | `app/shared/domain/exceptions.py` |
| `app/utils/security.py` | `app/shared/infrastructure/security.py` |
| `app/utils/columns.py` | `app/shared/infrastructure/base_repository.py`（合併） |
| `app/utils/logger.py` | `app/shared/infrastructure/logger.py` |
| `app/utils/csv_handler.py` | `app/admin/infrastructure/csv_handler.py` |
| `app/repositories/base.py` | `app/shared/infrastructure/base_repository.py` |
| `app/repositories/auth_repo.py` | `app/identity/infrastructure/postgres_user_repo.py` |
| `app/repositories/tutor_repo.py` | `app/catalog/infrastructure/postgres_tutor_repo.py` |
| `app/repositories/student_repo.py` | `app/catalog/infrastructure/postgres_student_repo.py` |
| `app/repositories/match_repo.py` | `app/matching/infrastructure/postgres_match_repo.py` |
| `app/repositories/session_repo.py` | `app/teaching/infrastructure/postgres_session_repo.py` |
| `app/repositories/exam_repo.py` | `app/teaching/infrastructure/postgres_exam_repo.py` |
| `app/repositories/review_repo.py` | `app/review/infrastructure/postgres_review_repo.py` |
| `app/repositories/message_repo.py` | `app/messaging/infrastructure/postgres_message_repo.py` |
| `app/repositories/stats_repo.py` | `app/analytics/infrastructure/postgres_stats_repo.py` |
| `app/models/auth.py` | `app/identity/api/schemas.py` |
| `app/models/tutor.py` | `app/catalog/api/schemas.py` |
| `app/models/student.py` | `app/catalog/api/schemas.py`（合併） |
| `app/models/match.py` | `app/matching/api/schemas.py` |
| `app/models/session.py` | `app/teaching/api/schemas.py` |
| `app/models/exam.py` | `app/teaching/api/schemas.py`（合併） |
| `app/models/review.py` | `app/review/api/schemas.py` |
| `app/models/message.py` | `app/messaging/api/schemas.py` |
| `app/models/stats.py` | `app/analytics/api/schemas.py` |
| `app/models/common.py` | `app/shared/api/schemas.py` |
| `app/routers/auth.py` | `app/identity/api/router.py` |
| `app/routers/tutors.py` | `app/catalog/api/tutor_router.py` |
| `app/routers/students.py` | `app/catalog/api/student_router.py` |
| `app/routers/subjects.py` | `app/catalog/api/subject_router.py` |
| `app/routers/matches.py` | `app/matching/api/router.py` |
| `app/routers/sessions.py` | `app/teaching/api/session_router.py` |
| `app/routers/exams.py` | `app/teaching/api/exam_router.py` |
| `app/routers/reviews.py` | `app/review/api/router.py` |
| `app/routers/messages.py` | `app/messaging/api/router.py` |
| `app/routers/stats.py` | `app/analytics/api/router.py` |
| `app/routers/admin.py` | `app/admin/api/router.py` |
| `app/routers/health.py` | `app/shared/api/health_router.py` |

### 9.2 新建（不存在於舊架構）

| 新檔案 | 說明 |
|--------|------|
| `app/shared/domain/types.py` | 共用型別別名 |
| `app/shared/domain/exceptions.py` | Domain 例外基底 |
| `app/identity/domain/entities.py` | User entity |
| `app/identity/domain/services.py` | AuthService |
| `app/identity/domain/ports.py` | IUserRepository |
| `app/catalog/domain/entities.py` | Tutor, Student entity |
| `app/catalog/domain/value_objects.py` | AvailabilitySlot, SubjectRate, Visibility |
| `app/catalog/domain/services.py` | TutorService, StudentService |
| `app/catalog/domain/ports.py` | ITutorRepository, IStudentRepository |
| `app/catalog/infrastructure/catalog_query_adapter.py` | 跨 Context 查詢 Adapter |
| `app/matching/domain/entities.py` | Match Aggregate Root |
| `app/matching/domain/value_objects.py` | MatchStatus, Action, Contract |
| `app/matching/domain/state_machine.py` | 狀態機純邏輯 |
| `app/matching/domain/services.py` | MatchDomainService |
| `app/matching/domain/ports.py` | IMatchRepository, ICatalogQuery |
| `app/matching/domain/exceptions.py` | 配對相關 Domain 例外 |
| `app/matching/application/match_app_service.py` | 配對 Use Case 編排 |
| `app/teaching/domain/entities.py` | Session, Exam entity |
| `app/teaching/domain/value_objects.py` | EditLog |
| `app/teaching/domain/services.py` | SessionService, ExamService |
| `app/teaching/domain/ports.py` | ISessionRepository, IExamRepository |
| `app/review/domain/entities.py` | Review Aggregate Root |
| `app/review/domain/value_objects.py` | ReviewType, Rating, LockWindow |
| `app/review/domain/services.py` | ReviewDomainService |
| `app/review/domain/ports.py` | IReviewRepository |
| `app/messaging/domain/entities.py` | Conversation, Message |
| `app/messaging/domain/services.py` | MessagingService |
| `app/messaging/domain/ports.py` | IMessageRepository |
| `app/analytics/query_service.py` | StatsQueryService |

---

## 10. 測試策略

### 10.1 測試金字塔

```
          ╱╲
         ╱  ╲          E2E 測試（少量）
        ╱ E2E╲         - 完整 API 打通測試
       ╱──────╲        - Docker Compose + httpx
      ╱ 整合   ╲       整合測試（中量）
     ╱ 測試     ╲      - Repository + 真實 DB
    ╱────────────╲     - Application Service + mock Port
   ╱  單元測試    ╲    單元測試（大量）— DDD 最大收益
  ╱                ╲   - Domain Entity 行為
 ╱__________________╲  - State Machine 所有轉換路徑
                       - Value Object 驗證
```

### 10.2 DDD 帶來的測試能力提升

**重構前**：只能寫整合測試（啟動 FastAPI + DB）

**重構後**：

```python
# 純單元測試 — 不需要 DB、不需要 FastAPI、毫秒級執行
class TestMatchStateMachine:
    def test_pending_accept_with_trial(self):
        result = resolve_transition(
            current=MatchStatus.PENDING,
            action=Action.ACCEPT,
            actor_is_parent=False, actor_is_tutor=True,
            actor_is_admin=False, actor_user_id=1,
            terminated_by=None, want_trial=True,
        )
        assert result == MatchStatus.TRIAL

    def test_parent_cannot_accept(self):
        with pytest.raises(PermissionDeniedError):
            resolve_transition(
                current=MatchStatus.PENDING,
                action=Action.ACCEPT,
                actor_is_parent=True, actor_is_tutor=False,
                ...
            )

    def test_cannot_pause_from_pending(self):
        with pytest.raises(InvalidTransitionError):
            resolve_transition(
                current=MatchStatus.PENDING,
                action=Action.PAUSE,
                ...
            )
```

### 10.3 建議的測試檔案結構

```
tests/
├── unit/                            # 純單元測試（無 DB）
│   ├── matching/
│   │   ├── test_state_machine.py    # 所有狀態轉換路徑
│   │   ├── test_match_entity.py     # Match entity 行為
│   │   └── test_value_objects.py    # MatchStatus, Contract
│   ├── review/
│   │   ├── test_review_entity.py    # 鎖定邏輯
│   │   └── test_review_type.py      # 角色驗證
│   └── teaching/
│       └── test_session_entity.py   # 編輯 diff 計算
│
├── integration/                     # 整合測試（需要 DB）
│   ├── test_match_app_service.py    # Application Service 完整流程
│   ├── test_auth_service.py
│   └── test_repos.py               # Repository 正確性
│
└── e2e/                             # 端對端測試
    ├── test_match_api.py            # HTTP → API → DB 打通
    └── test_auth_api.py
```

---

## 11. 風險與注意事項

### 11.1 風險評估

| 風險 | 影響 | 緩解措施 |
|------|------|---------|
| Import 路徑大量變更導致遺漏 | RuntimeError | Phase 1 放 re-export shim，逐步移除 |
| 前端因 API 格式變更而壞掉 | 使用者可見 | API path + response 格式嚴格不變 |
| 團隊不熟悉 DDD 概念 | 開發速度下降 | 先搬簡單的 BC（Identity），熟練後再搬核心 |
| 過渡期間新舊架構混用 | 維護成本增加 | 每搬完一個 BC 就立刻刪除舊 Router 的 shim |

### 11.2 給團隊的提醒

1. **Domain Layer 裡不准出現 `import fastapi`、`import psycopg2`**——這是最重要的紀律
2. **每個 PR 只搬一個 BC**——不要一次搬太多，review 會很痛苦
3. **搬遷不等於重寫**——SQL 查詢、Pydantic Schema 基本不用改，只是換位置
4. **先跑測試再 push**——每搬完一個 Phase 至少跑一次完整的 API 測試

### 11.3 不在本次範圍（未來可考慮）

- **Domain Event**：例如 `MatchAccepted` 事件觸發建立第一堂 Session。目前用同步呼叫即可，未來可改 Event Bus
- **CQRS 完整實作**：目前 Analytics 已是 Query Side 雛形，但不需要獨立 Read Model
- **依賴注入容器**：目前用工廠函式手動組裝，足夠用。未來可引入 `dependency-injector` 套件

---

## 附錄 A：Context Map 全圖

```
                      ┌──────────────────┐
                      │  Shared Kernel   │
                      │  types, exceptions│
                      │  database, config │
                      └────────┬─────────┘
                               │
            ┌──────────────────┼───────────────────┐
            │                  │                    │
     ┌──────▼──────┐   ┌──────▼──────┐   ┌────────▼───────┐
     │  Identity   │   │   Catalog   │   │   Messaging    │
     │             │   │             │   │                │
     │ User        │   │ Tutor       │   │ Conversation   │
     │ Auth        │   │ Student     │   │ Message        │
     │ JWT         │   │ Subject     │   │                │
     └──────┬──────┘   └──────┬──────┘   └────────────────┘
            │                 │
            │          ┌──────▼──────┐
            │          │  Matching   │◄──── Core Domain
            │          │             │
            │          │ Match (AR)  │
            │          │ StateMachine│
            │          │ Contract    │
            │          └──┬───────┬──┘
            │             │       │
            │      ┌──────▼───┐ ┌─▼──────────┐
            │      │ Teaching │ │  Review     │
            │      │          │ │             │
            │      │ Session  │ │ Review (AR) │
            │      │ Exam     │ │ Rating      │
            │      │ EditLog  │ │ LockWindow  │
            │      └──────┬───┘ └─────┬───────┘
            │             │           │
            │      ┌──────▼───────────▼──┐
            │      │     Analytics       │ ← Query Side
            │      │ (read-only, no      │
            │      │  domain entities)   │
            │      └─────────────────────┘
            │
     ┌──────▼────────────────────────────┐
     │            Admin                   │ ← Infrastructure
     │  (import/export, reset, status)    │
     └────────────────────────────────────┘

箭頭方向 = 依賴方向（A → B 代表 A 依賴 B）
```

---

## 附錄 B：main.py 最終樣貌

```python
# app/main.py（Phase 9 完成後）
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.shared.infrastructure.config import settings
from app.shared.domain.exceptions import DomainException

# 各 BC 的 router
from app.identity.api.router import router as auth_router
from app.catalog.api.tutor_router import router as tutor_router
from app.catalog.api.student_router import router as student_router
from app.catalog.api.subject_router import router as subject_router
from app.matching.api.router import router as match_router
from app.teaching.api.session_router import router as session_router
from app.teaching.api.exam_router import router as exam_router
from app.review.api.router import router as review_router
from app.messaging.api.router import router as message_router
from app.analytics.api.router import router as stats_router
from app.admin.api.router import router as admin_router
from app.shared.api.health_router import router as health_router

# ... lifespan, middleware 設定不變 ...

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(tutor_router)
app.include_router(student_router)
app.include_router(subject_router)
app.include_router(match_router)
app.include_router(session_router)
app.include_router(exam_router)
app.include_router(review_router)
app.include_router(message_router)
app.include_router(stats_router)
app.include_router(admin_router)
```

---

*施工說明書完*
