# Tutor Matching and Rating Platform — System Specification

**Document ID:** TMP-SPEC-2026-001
**Version:** v6.0
**Created:** 2026-03-28
**Last Updated:** 2026-05-16

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Technical Design](#3-technical-design)
4. [Roles and Permission Model](#4-roles-and-permission-model)
5. [Functional Modules](#5-functional-modules)
6. [Database Design](#6-database-design)
7. [API Specification](#7-api-specification)
8. [Frontend Routes and Components](#8-frontend-routes-and-components)
9. [Asynchronous Task Engine](#9-asynchronous-task-engine)
10. [Team Responsibilities](#10-team-responsibilities)
11. [Development Schedule](#11-development-schedule)
12. [Demonstration Flow](#12-demonstration-flow)
13. [Appendix](#13-appendix)

---

## 1. Project Overview

### 1.1 Summary

TMRP is a tutor-matching web platform — conceptually a domain-scoped version of "104 人力銀行" focused on private tutoring. A typical flow: a parent searches for tutors by subject and hourly rate, reviews a tutor's profile and historical ratings, exchanges messages, then sends a match invitation. The tutor accepts, rejects, or counters with a trial period. Once teaching begins, the tutor records lesson logs and exam scores; the parent watches progress under the visibility rules the tutor controls. When the engagement ends, both sides exchange structured ratings.

The three core capabilities are:

| Capability | Description |
|---|---|
| **Matching** | Parent searches tutors → in-app messaging → invitation → tutor accepts → engagement begins |
| **Teaching management** | Tutor logs sessions and exam scores; parents see what tutors have marked visible |
| **Three-way reviews** | After the match ends, parent rates tutor; tutor rates student and parent |

### 1.2 Course Context

The project is the final group assignment for a university-level SQL course originally requiring MS Access. The database was first prototyped in Access to meet the coursework constraint, then migrated to PostgreSQL 16 so the system runs anywhere Docker is available. The Access prototype remains the source of the schema design discussed in the slides; the running implementation is PostgreSQL.

Course requirements:

- Demonstrate a normalised relational schema with foreign-key relationships
- In-class oral presentation with a live system demo

### 1.3 Design Goals

| Goal | Approach |
|---|---|
| Meet course requirements | Ship a documented relational schema with FK constraints, indexes, and triggers; show the schema and live data during the demo |
| Apply industry practices | Three-tier architecture, DDD-style bounded contexts, RESTful API, JWT auth, container-based deployment |
| Reproducible deployment | `docker compose up` provisions the full stack (DB + API + worker + reverse proxy); a Windows `start.bat` covers local non-Docker development |

### 1.4 Timeline

Five-week development cycle culminating in an oral presentation and a live demonstration.

---

## 2. System Architecture

### 2.1 Component Overview

Four processes cooperate over HTTP and a shared PostgreSQL database:

```
   Browser (Vue 3 SPA)
        │  HTTP / JSON
        ▼
   Nginx (web container)            serves SPA assets, proxies /api/* to api:8000
        │
        ▼
   FastAPI (api container)          REST API, JWT auth, domain services, repositories
        │  psycopg2 connection pool
        ▼
   PostgreSQL 16 (db container)     persistent volume: pgdata
        ▲
        │
   Huey worker (worker container)   CSV import/export, seed data, stats, scheduled
                                    cleanup; SqliteHuey queue at data/huey.db
                                    (shared volume with api)
```

### 2.2 Process Responsibilities

| Process | Technology | Responsibility |
|---|---|---|
| **Web (Nginx)** | nginx-unprivileged 1.x | Serve compiled SPA, terminate the inbound HTTP request, reverse-proxy `/api/*` to the API container, apply an edge-layer rate limit |
| **Frontend (Vue)** | Vue 3 + Vite + Pinia + Vue Router + Axios | All in-browser UI: login, dashboards, search, messaging, match management, reviews, stats |
| **Backend (FastAPI)** | FastAPI + Pydantic + psycopg2 | Authentication, business logic, state-machine enforcement, repository-backed persistence |
| **Worker (Huey)** | huey 2.5 + SqliteHuey | Statistics aggregation, scheduled maintenance (review lock, blacklist cleanup, rate-limit pruning) |
| **Database (PostgreSQL)** | PostgreSQL 16-alpine | Authoritative store for all business data, rate-limit hits, idempotency keys, audit log, refresh-token blacklist |

### 2.3 Technology Stack

| Layer | Technology | Version |
|---|---|---|
| Frontend framework | Vue 3 | 3.5.13 |
| Build tool | Vite | 6.0.5 |
| State management | Pinia | 2.3.0 |
| Routing | Vue Router | 4.5.0 |
| HTTP client | Axios | 1.7.9 |
| Charts | Chart.js + vue-chartjs | 4.5.1 / 5.3.3 |
| CSS framework | Tailwind CSS | 4.2.2 |
| Backend framework | FastAPI | 0.115.6 |
| ASGI server | Uvicorn | 0.34.0 |
| Data validation | Pydantic | 2.10.4 |
| Database driver | psycopg2 | ≥2.9.11 |
| Password hashing | bcrypt | 4.2.1 |
| JWT | PyJWT | 2.9.0 |
| Task queue | Huey | 2.5.2 |
| Database | PostgreSQL | 16 (alpine) |
| Reverse proxy | Nginx | 1.x (nginx-unprivileged) |
| Container runtime | Docker / Docker Compose | n/a |

---

## 3. Technical Design

### 3.1 Source Tree

The codebase is split into two top-level applications: a Python backend and a Vue frontend, plus repository-root files for Docker orchestration and secrets management.

#### 3.1.1 Repository Layout

```
project-root/
├── docker-compose.yml              # Production stack (db, api, worker, web)
├── docker-compose.override.yml     # Auto-loaded in dev; binds db→127.0.0.1:5433, api→127.0.0.1:8001
├── docker-compose.run.yml          # Optional local-Postgres convenience configuration
├── .env / .env.example             # Repo-root env (DB_USER, DB_NAME consumed by compose)
├── .pre-commit-config.yaml         # Lint/format hooks
├── .gitleaks.toml                  # Secrets detection
├── README.md                       # Project overview and quick-start
├── SECURITY.md                     # Security controls and production-deployment checklist
├── secrets/                        # Docker secret files (gitignored): db_password, jwt_secret_key, admin_password, jwt_secret_key_previous
├── scripts/                        # Helper shell scripts (check-prod-compose, pin-base-images)
├── docs/                           # Specifications and design notes (this file, architecture, schema)
├── tutor-platform-api/             # Python backend
└── tutor-platform-web/             # Vue frontend
```

#### 3.1.2 Backend (`tutor-platform-api/`)

The backend is organised into DDD-style bounded contexts. Each context owns its API, application, domain, and infrastructure layers. Cross-cutting concerns live under `shared/` and `middleware/`.

```
tutor-platform-api/
├── Dockerfile
├── requirements.txt / requirements.lock
├── docker-entrypoint.sh             # Reads /run/secrets, constructs DATABASE_URL, launches uvicorn
├── start.bat                        # Local one-click launcher (worker + uvicorn + Vite)
├── .env.example                     # Local development template
├── .env.docker.example              # Container template (non-secret settings only)
│
├── app/
│   ├── main.py                      # FastAPI app, lifespan, middleware wiring, exception handlers
│   ├── init_db.py                   # Idempotent schema DDL, subject seed, admin bootstrap
│   ├── worker.py                    # SqliteHuey instance + JSON serialiser
│   │
│   ├── shared/                      # Cross-cutting kernel
│   │   ├── api/                     # ApiResponse envelope, validators, constants
│   │   ├── domain/                  # DomainException, NotFoundError, PermissionDeniedError, ...
│   │   └── infrastructure/          # config (Settings), database (pool), security (bcrypt/JWT), logger, base_repository
│   │
│   ├── identity/                    # Bounded context: auth, accounts, password history
│   ├── catalog/                     # Bounded context: tutors, students, subjects, availability
│   ├── matching/                    # Bounded context: matches, state machine, idempotency
│   ├── teaching/                    # Bounded context: session logs, exams, edit logs
│   ├── review/                      # Bounded context: three-way ratings, 7-day lock
│   ├── messaging/                   # Bounded context: conversations, messages
│   ├── analytics/                   # Bounded context: income/expense stats, student-progress
│   ├── admin/                       # Bounded context: CSV import/export, seed, system reset, user admin
│   │
│   ├── middleware/                  # request_id, body_size_limit, security_headers, access_log, user_quota, csrf, rate_limit
│   ├── tasks/                       # Huey task modules (stats_tasks, scheduled, import_export, seed_tasks)
│   └── utils/                       # Helpers
│
├── seed/                            # Fake-data generator used by the seed task
├── data/                            # Runtime: huey.db, mounted as a Docker volume
└── tests/                           # Pytest suite (state machine, services, integration)
```

Each bounded context follows the same internal layering:

```
<context>/
├── api/             # FastAPI routers, request/response schemas, dependencies
├── application/     # Use-case services (compose domain + infrastructure)
├── domain/          # Entities, value objects, domain services, exceptions (no framework dependencies)
└── infrastructure/  # Postgres repositories, external adapters
```

#### 3.1.3 Frontend (`tutor-platform-web/`)

```
tutor-platform-web/
├── Dockerfile                       # Vite build → nginx-unprivileged
├── nginx.conf                       # /api/* → api:8000, SPA fallback, edge rate limit, security headers
├── vite.config.js
├── package.json
├── scripts/check-no-v-html.mjs      # Pre-build lint guard (rejects v-html)
│
└── src/
    ├── main.js
    ├── App.vue
    ├── constants.js                 # Shared enums (roles, match status, action names)
    │
    ├── router/index.js              # Route table + role-based navigation guards
    ├── stores/                      # Pinia: auth, tutor, toast, notifications
    ├── api/                         # Axios services, one file per resource (+ baseURL, authHandler)
    │
    ├── views/                       # Page-level components
    │   ├── LoginView.vue / RegisterView.vue / NotFoundView.vue
    │   ├── parent/                  # Dashboard, Search, TutorDetail, MatchDetail, Students, Profile, Expense
    │   ├── tutor/                   # Dashboard, Profile, MatchDetail, Income
    │   ├── messages/                # ConversationList, Chat
    │   └── admin/                   # AdminDashboard
    │
    ├── components/                  # common, match, review, session, stats, tutor
    ├── composables/                 # useMatchDetail, useConfirm
    └── utils/                       # highlight, format
```

### 3.2 Unified API Response Envelope

Every API response carries a uniform envelope so the frontend can handle success and failure identically:

```json
{
  "success": true,
  "data": { "...": "..." },
  "message": "optional human-readable note"
}
```

Success example — fetching the authenticated user:

```json
{
  "success": true,
  "data": { "user_id": 1, "role": "tutor", "display_name": "Wang" },
  "message": null
}
```

Failure example — operation rejected by domain rule:

```json
{
  "success": false,
  "data": null,
  "message": "This tutor is not currently accepting new students"
}
```

Paginated response — 87 total results, current page 1:

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

Implementation:

```python
# app/shared/api/schemas.py
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

Domain exceptions map to HTTP status codes through centralised handlers registered on the FastAPI app:

```python
# app/shared/domain/exceptions.py
class DomainException(Exception):
    status_code: int = 400

class NotFoundError(DomainException):
    status_code = 404

class PermissionDeniedError(DomainException):
    status_code = 403

class TooManyRequestsError(DomainException):
    status_code = 429
```

Unhandled exceptions yield a 500 response that always carries the `X-Request-ID` so an incident can be traced back through the structured access log.

### 3.3 Layered Architecture per Bounded Context

The backend follows DDD layering inside each context. The API layer is a thin adapter; persistence is isolated behind repository interfaces; business rules live in the domain layer.

| Layer | Responsibility | Dependency Direction |
|---|---|---|
| **API** | HTTP routing, request/response schemas, role guards | Depends on application |
| **Application** | Use-case orchestration, transaction boundaries | Depends on domain + infrastructure |
| **Domain** | Entities, value objects, domain services, invariants | No outward dependencies |
| **Infrastructure** | PostgreSQL repositories, external adapters | Implements domain interfaces |

The match state machine is a representative example — pure logic with no framework or database coupling, unit-testable in isolation:

```python
# app/matching/domain/state_machine.py (excerpt)
TRANSITIONS: dict[tuple[MatchStatus, Action], Transition] = {
    (MatchStatus.PENDING, Action.CANCEL):
        Transition(MatchStatus.CANCELLED, AllowedActor.PARENT),
    (MatchStatus.PENDING, Action.REJECT):
        Transition(MatchStatus.REJECTED, AllowedActor.TUTOR),
    (MatchStatus.PENDING, Action.ACCEPT):
        Transition(None, AllowedActor.TUTOR),  # final status depends on want_trial
    (MatchStatus.TRIAL, Action.CONFIRM_TRIAL):
        Transition(MatchStatus.ACTIVE, AllowedActor.EITHER),
    # ... full table in §5.4
}
```

### 3.4 Database Connection Management

The API process manages a single psycopg2 connection pool (default min 5, max 20) created in the FastAPI lifespan hook. Each request borrows a connection from the pool and returns it on completion. A per-user concurrency middleware caps how many simultaneous connections any one authenticated caller can hold (default 5), preventing one client from monopolising the pool.

```python
# app/shared/infrastructure/database.py (concept)
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager

pool: ThreadedConnectionPool  # initialised in lifespan

@contextmanager
def get_connection():
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
```

The pool is built from `DATABASE_URL`, which the Docker entrypoint constructs at runtime from `/run/secrets/db_password` plus the non-secret host/db/user environment variables — passwords never appear in env vars or in the build context.

### 3.5 Configuration and Secrets

Configuration is split by sensitivity:

- **Non-secret environment** lives in `.env` / `.env.docker` files (host, database name, user, log level, cookie flags, etc.).
- **Secrets** (database password, JWT signing key, bootstrap admin password) live in Docker secret files mounted at `/run/secrets/*`. They are never written to environment variables and never enter the build context.

| Setting | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | (built from secret) | psycopg2 connection string; constructed by `docker-entrypoint.sh` |
| `JWT_SECRET_KEY` | (required) | JWT HMAC key; min 32 hex characters |
| `JWT_SECRET_KEY_PREVIOUS` | (optional) | Previous key during a rotation window |
| `JWT_SECRET_KEY_PREVIOUS_EXPIRES_AT` | (required if PREVIOUS set) | ISO-8601 UTC deadline ≤ 7 days out |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_EXPIRE_MINUTES` | `5` | Access-token lifetime; hard-capped at 10 by startup validator |
| `ADMIN_USERNAME` | (required) | Bootstrap admin login; cannot be the literal `admin` in production |
| `ADMIN_PASSWORD` | (required) | Min 16 chars, all four character classes |
| `REVIEW_LOCK_DAYS` | `7` | Days after which a review locks |
| `HUEY_DB_PATH` | `data/huey.db` | SqliteHuey queue file |
| `LOG_FILE` / `LOG_LEVEL` / `LOG_FORMAT` | `logs/app.log` / `INFO` / `json` | Logging |
| `COOKIE_SECURE` | `true` | Auth cookies carry the `Secure` attribute; must be `true` when `DEBUG=false` |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allow-list |
| `DB_POOL_MIN` / `DB_POOL_MAX` | `5` / `20` | psycopg2 pool sizing |
| `DB_PER_USER_QUOTA` | `5` | Max concurrent in-flight requests per authenticated user |
| `DEBUG` | `false` | Enables developer affordances; gated by startup validator |
| `ENABLE_DOCS` | `false` | Exposes `/docs`, `/redoc`, `/openapi.json`; rejected at startup unless `DEBUG=true` |

The frontend reads `VITE_API_BASE_URL` at build time; in production this is an empty string so requests are emitted as relative paths (`/api/...`) and proxied by the web container's Nginx.

### 3.6 Structured Logging

All log lines are emitted as JSON to both stdout and a rotating file. Every record carries `request_id`, `user_id` (when authenticated), and the relevant resource identifiers. Sensitive fields — passwords, tokens, secrets — are redacted by the logger before serialisation.

```
{"ts":"2026-04-15T14:23:01Z","level":"INFO","request_id":"a1b2c3","user_id":17,"event":"login.success","username":"john_parent"}
{"ts":"2026-04-15T14:23:05Z","level":"WARNING","request_id":"d4e5f6","user_id":42,"event":"match.transition.rejected","match_id":42,"current":"trial","action":"pause"}
{"ts":"2026-04-15T14:25:30Z","level":"ERROR","request_id":"g7h8i9","event":"db.execute_failed","sql_op":"insert_session"}
```

### 3.7 Local One-Click Launch

For local development without Docker, `start.bat` opens three terminals: the Huey worker, the FastAPI server (`uvicorn --reload`), and the Vite dev server. Once the API is healthy:

```
================================================
  All services running
  API Server:   http://localhost:8000
  Swagger UI:   http://localhost:8000/docs   (when DEBUG=true and ENABLE_DOCS=true)
  Frontend:     http://localhost:5173
================================================
```

For production-style local runs, `docker compose up -d --build` brings up the entire stack and the frontend is reachable at `http://localhost/`.

### 3.8 Frontend Axios Wrapper

The frontend funnels all API traffic through a configured Axios instance that:

1. Carries cookies on every request (auth, refresh, CSRF are all HttpOnly cookies).
2. Attaches the `X-CSRF-Token` header on mutating methods, sourced from the `csrf_token` cookie.
3. Intercepts 401 responses and attempts a refresh, retrying the original request on success or redirecting to `/login` on failure.
4. Unwraps the `ApiResponse` envelope so callers receive `data` directly; failures become rejected promises carrying the `message`.

---

## 4. Roles and Permission Model

### 4.1 User Roles

| Role | Account Creation | Responsibility |
|---|---|---|
| **Admin** | Bootstrapped from `ADMIN_USERNAME` + secret on first start-up | System administration: CSV import/export, fake-data seed, system reset, user administration |
| **Parent** | Self-registration | Demand side: search tutors, manage children, send invitations, write reviews |
| **Tutor** | Self-registration | Supply side: maintain profile and availability, accept/reject invitations, record sessions and exams |

### 4.2 Permission Matrix

| Capability | Admin | Parent | Tutor |
|---|:--:|:--:|:--:|
| Admin console | ✓ | ✗ | ✗ |
| CSV import/export | ✓ | ✗ | ✗ |
| Generate fake data | ✓ | ✗ | ✗ |
| Reset database | ✓ | ✗ | ✗ |
| List all accounts | ✓ | ✗ | ✗ |
| Search tutors | ✓ | ✓ | ✗ |
| Manage children | ✗ | ✓ | ✗ |
| Send invitation | ✗ | ✓ | ✗ |
| Accept / reject invitation | ✗ | ✗ | ✓ |
| Write session log | ✗ | ✗ | ✓ |
| View session log | ✗ | Per `visible_to_parent` | ✓ (own) |
| Add exam record | ✗ | ✓ | ✓ |
| View exam record | ✗ | Per `visible_to_parent` | ✓ (own) |
| Write review | ✗ | ✓ (parent→tutor) | ✓ (tutor→student, tutor→parent) |
| Send messages | ✓ | ✓ | ✓ |
| Income statistics | ✗ | ✗ | ✓ (own) |
| Expense statistics | ✗ | ✓ (own) | ✗ |
| Edit tutor profile | ✗ | ✗ | ✓ (own) |

### 4.3 Page Access Rules

The frontend router enforces a navigation guard that calls `auth.ensureVerified()` — which hits `GET /api/auth/me` — before granting access to any role-gated route. `localStorage.user` is a cache only; the server is authoritative.

| User state | Target route | Behaviour |
|---|---|---|
| Unauthenticated | Any guarded route | Redirected to `/login` |
| Parent | `/tutor/*` or `/admin/*` | Redirected to `/parent` |
| Tutor | `/parent/*` or `/admin/*` | Redirected to `/tutor` |
| Admin | Any route | Permitted |

The backend independently enforces the same rules via the `require_role()` dependency on every protected endpoint, so client-side bypass attempts cannot escalate privileges.

---

## 5. Functional Modules

The functional surface is organised into eleven modules (A–K). Each module corresponds to a coherent slice of user-facing behaviour.

### 5.1 Module A — Authentication

#### Registration

1. The user picks a role (parent or tutor).
2. The user supplies username, password, display name, phone, and email.
3. The password is bcrypt-hashed before persistence; the plaintext is never stored.
4. If the role is tutor, an empty tutor profile is created so the user can edit it after first login.

Password policy: minimum 10 characters, must include both letters and digits (enforced server-side). The last five hashes per user are retained in `password_history` and re-use is rejected on password change.

#### Login and Session Lifecycle

1. The user submits username and password.
2. On success, the backend issues an access token (5-minute default, hard-capped at 10) and a refresh token (7 days). Both are delivered as `HttpOnly` cookies, plus a non-`HttpOnly` `csrf_token` cookie for double-submit CSRF.
3. The frontend's Axios wrapper carries the cookies automatically. When the access token expires, the wrapper transparently calls `/api/auth/refresh` and retries the original request.
4. `POST /api/auth/logout` invalidates the refresh token by recording its JTI in `refresh_token_blacklist` — checked on every subsequent refresh attempt across all API workers.

#### Admin Bootstrap

The admin account is not registered via the API. On first start-up the API container reads `ADMIN_USERNAME` (env) and `ADMIN_PASSWORD` (Docker secret) and inserts the row. The startup validator refuses to boot if either is at a placeholder value, if the password fails the strength rule, or if the username is the literal `admin` while `DEBUG=false`.

### 5.2 Module B — Messaging

One-to-one plain-text messaging between any two registered users.

| Rule | Detail |
|---|---|
| Uniqueness | Exactly one conversation per ordered pair of users; a database trigger swaps `(user_a_id, user_b_id)` so the smaller ID is always first, and a unique index enforces it |
| Content | Plain text only — no attachments, stickers, or read receipts |
| Initiation | Any user may open a conversation with any other user; opening from a tutor detail page reuses any existing conversation |

| UI | Description |
|---|---|
| Conversation list | Sorted by `last_message_at`; shows the counterparty name and the most recent message snippet |
| Chat view | Chronological message stream with a text input and send button; messages are fetched in pages via a `before_id` cursor (limit 1–500) |
| Rate limits | 30 messages per conversation per minute and 100 messages per user per hour (global) |

### 5.3 Module C — Tutor Search and Profile

#### Search

Filters can be combined:

| Filter | Mechanism | Notes |
|---|---|---|
| Subject | Drop-down | Restricts to tutors teaching the chosen subject |
| Hourly rate range | Min / max numeric inputs | Filters on `tutor_subjects.hourly_rate` |
| Minimum rating | Numeric input | Filters on the materialised review-stats average |
| School / university | Text input | Substring match on `tutors.university` |

Sort options: highest rating, lowest hourly rate, most recently registered.

Result cards always show name, average rating, and review count. Tutors control visibility of: university, department, grade year, hourly rate, and subjects. Hidden fields are stripped server-side before the response is sent — `localStorage` tampering on the client cannot expose them.

#### Tutor Detail

| Section | Content |
|---|---|
| Self-introduction | Free-text bio and teaching experience |
| Reviews | Radar chart of the four numeric rating dimensions and a paginated review list |
| Availability | Weekly time-slot calendar |
| Capacity | Active students / `max_students` |
| Actions | "Send message", "Send invitation" |

#### Profile Editing

| Category | Editable fields |
|---|---|
| Basic | Name, university, department, grade year, self-intro, teaching experience |
| Teaching | Teachable subjects (per-subject hourly rate), `max_students` |
| Availability | Weekly recurring time slots (day of week + start/end times) |
| Visibility | Per-field flags: `show_university`, `show_department`, `show_grade_year`, `show_hourly_rate`, `show_subjects` |

### 5.4 Module D — Matching and Contracts

#### Lifecycle

A match progresses through a defined set of states. The state machine lives in `app/matching/domain/state_machine.py` and is unit-tested independently of HTTP and persistence.

```
                  [Parent sends invitation]
                              │
                           pending
                          /        \
              [Parent cancels]    [Tutor rejects]
                  │                    │
              cancelled              rejected
                                       
                  [Tutor accepts, no trial]
                              │
                           active
                              
                  [Tutor accepts, with trial]
                              │
                            trial
                           /       \
              [Either confirms]   [Either rejects]
                  │                    │
                active                rejected
                  │
                  ├──── pause ──── paused
                  │                  │
                  └─── resume ◄──────┘
                  │
                  │   [Either party initiates termination]
                  ▼
              terminating
              /          \
   [Other party agrees]  [Other party disagrees]
       │                       │
     ended            revert to active or paused
       │
   [Reviews open; lock after 7 days]
```

#### Transition Table

| Current Status | Action | Allowed Actor | New Status |
|---|---|---|---|
| `pending` | `cancel` | Parent | `cancelled` |
| `pending` | `reject` | Tutor | `rejected` |
| `pending` | `accept` | Tutor | `trial` if `want_trial=true`, else `active` |
| `trial` | `confirm_trial` | Either party | `active` |
| `trial` | `reject_trial` | Either party | `rejected` |
| `active` | `pause` | Either party | `paused` |
| `active` | `terminate` | Either party | `terminating` |
| `paused` | `resume` | Either party | `active` |
| `paused` | `terminate` | Either party | `terminating` |
| `terminating` | `agree_terminate` | Other party only | `ended` |
| `terminating` | `disagree_terminate` | Other party only | Reverts to pre-termination status (`active` or `paused`) |

Admins bypass actor checks except for `OTHER_PARTY` transitions, which always require the non-initiating party to act — an admin cannot unilaterally finalise a termination.

#### Contract Terms

Recorded on the match record:

| Field | Notes |
|---|---|
| `hourly_rate` | Per-hour fee |
| `sessions_per_week` | Agreed weekly session count |
| `start_date` | Engagement start date |
| `end_date` | Engagement end date (filled in at termination) |
| `penalty_amount` | Early-termination penalty |
| `trial_price` | Trial-session rate (typically lower than `hourly_rate`) |
| `trial_count` | Agreed number of trial sessions |
| `contract_notes` | Free-text addenda |

#### Invitation Payload

| Field | Required | Notes |
|---|:--:|---|
| `student_id` | ✓ | One of the parent's registered children |
| `subject_id` | ✓ | Must be a subject the tutor teaches |
| `hourly_rate` | ✓ | Parent's proposed rate |
| `sessions_per_week` | ✓ | Parent's proposed cadence |
| `want_trial` | ✓ | If true, accept sends the match into `trial` |
| `invite_message` | optional | Free-text message to the tutor |

Invitations carry an `Idempotency-Key` header; duplicates are deduplicated via the `idempotency_keys` table so a retried request never creates a second match. Per-(tutor, parent) bucket rate limit: 10 invites per hour.

### 5.5 Module E — Session Logs

After every lesson the tutor records one session entry.

| Field | Required | Notes |
|---|:--:|---|
| `session_date` | ✓ | Date picker |
| `hours` | ✓ | Decimal (e.g. 1.5) |
| `content_summary` | ✓ | What was taught |
| `homework` | optional | Assigned homework |
| `student_performance` | optional | In-class observation |
| `next_plan` | optional | Plan for the next session |
| `visible_to_parent` | ✓ | Defaults to `false`; the tutor decides per session |

Permissions:

- Only the match's tutor may create or edit sessions.
- Parents see only sessions where `visible_to_parent=true`.
- The parent dashboard surfaces the most recent visible sessions per child.

Edit history: every edit appends one row per changed field to `session_edit_logs` (field name, old value, new value, edited-at), giving a Google-Docs-style audit trail. Edit-log access is gated to match participants.

Rate limit: 10 session creations per match per minute.

### 5.6 Module F — Exam Records

| Field | Required | Notes |
|---|:--:|---|
| `exam_date` | ✓ | Date picker |
| `subject_id` | ✓ | From the subject catalogue |
| `exam_type` | ✓ | One of: 段考 / 小考 / 模擬考 / 其他 (mid-term, quiz, mock, other) |
| `score` | ✓ | Numeric |
| `visible_to_parent` | ✓ | Same semantics as session logs |

Permissions:

- Both tutors and parents may add exam records.
- Tutor-added records honour `visible_to_parent`.
- Parent-added records are always visible to that parent.

Progress delta is not stored; the frontend computes consecutive differences from a same-subject query (e.g. 72 → 85 → 90 yields deltas of +13 and +5).

Rate limit: 20 exam writes per student per user per minute.

### 5.7 Module G — Three-Way Review System

A finished match opens three independent review directions:

1. Parent → tutor (teaching quality?)
2. Tutor → student (learning attitude?)
3. Tutor → parent (cooperation?)

#### Dimensions

**Parent → tutor**

| Dimension | Scale |
|---|---|
| Teaching quality | 1–5 |
| Punctuality | 1–5 |
| Student progress | 1–5 |
| Communication | 1–5 |
| Personality comment | Free text |
| Overall comment | Free text |

**Tutor → student**

| Dimension | Scale |
|---|---|
| Learning attitude | 1–5 |
| Homework completion | 1–5 |
| Personality comment | Free text |
| Overall comment | Free text |

**Tutor → parent**

| Dimension | Scale |
|---|---|
| Cooperation (punctuality, no last-minute cancellations) | 1–5 |
| Communication (responsiveness, respect) | 1–5 |
| Payment timeliness | 1–5 |
| Personality comment | Free text |
| Overall comment | Free text |

#### Rules

| Rule | Detail |
|---|---|
| Trigger | Reviews open only after the match reaches `ended` |
| Cardinality | One review per `(match_id, reviewer_user_id, review_type)` |
| Edit window | The author may edit within `REVIEW_LOCK_DAYS` (default 7) |
| Lock mechanism | A scheduled task (`lock_expired_reviews`, daily 03:00 UTC) sets `is_locked=true` on expired rows; the `PATCH` endpoint also re-checks the timestamp on every call |

#### Presentation

- **Tutor detail page** — radar chart of the four numeric dimensions, sourced from the `v_review_stats` materialised view, plus a paginated review list.
- **Match detail page** — all three directions' reviews shown to match participants only.

### 5.8 Module H — Dashboards

The dashboard is the first page each user sees after login.

#### Tutor Dashboard

| Block | Content |
|---|---|
| Summary cards | Active students / `max_students`, current month income, pending invitation count |
| Pending | Invitations awaiting response |
| In progress | All non-terminal matches (active, trial, paused) with click-through to detail |

#### Parent Dashboard

| Block | Content |
|---|---|
| Children list | Each child's name and current match status |
| Outgoing invitations | Sent but not yet answered |
| Recent activity | Latest visible session logs across all children |
| Latest exam scores | Latest visible exam records per child |

**Implementation note:** "Recent activity" and "Latest exam scores" have no cross-match aggregation endpoint. The frontend fans out to `GET /api/matches/{match_id}/sessions` and the exam endpoints once per active match per child (N matches → N requests).

### 5.9 Module I — Statistics and Reports

#### Tutor Income

- Group by month / student / subject.
- Formula: Σ(`hours` × `hourly_rate`) over sessions in the chosen window.
- Rendered as bar chart plus tabular breakdown.
- Computation runs asynchronously via Huey so the UI stays responsive.

#### Parent Expense

- Symmetric to tutor income; group by month / child / subject.
- Same formula and dispatch model.

#### Student Progress

- **Line chart** — X axis exam date, Y axis score, with subject filter.
- **Table** — exam-by-exam listing with the delta from the previous same-subject score.
- Synchronous endpoint; access is gated to the student's parent, any tutor with an active match for that student, or an admin.

### 5.10 Module J — Import / Export and Fake Data

#### Export

- All exportable tables can be downloaded as CSV.
- `users` and `password_history` are excluded from the exportable list (they contain password hashes).
- A "one-click export-all" endpoint streams a ZIP of every exportable table.

#### Import

- Two mutually exclusive modes selected by query string:
  - **Upsert** (`?upsert=true`) — primary-key match, update if present, insert if absent.
  - **Overwrite** (`?clear_first=true`, admin only) — truncate the target table and bulk insert.
- Body cap is 50 MB; the `Content-Type` is validated as `text/csv` (or `application/zip` for import-all). Per-file row cap: 50 000 rows.
- These admin routes currently execute synchronously inside the request handler; the corresponding Huey task definitions exist in `app/tasks/import_export.py` but are not dispatched by the current routes.

#### Fake Data Generator

A built-in generator produces realistic seed data (Taiwanese names, university names, sensible rating distributions, plausible review comments) so the demo dataset can be reproduced with a single click. The Huey task definition exists in `app/tasks/seed_tasks.py`; the current admin `/seed` route runs the generator synchronously.

### 5.11 Module K — Admin Console

| Function | Description |
|---|---|
| Import / Export | Per-table CSV operations and a one-click all-tables ZIP variant |
| Database reset | Two-step flow with a 5-minute reset token and password re-confirmation; automatic backup (including `users`) before truncation; limited to once per admin per 7 days |
| User administration | List all accounts; force password reset (revokes all of the user's refresh tokens via `user_token_revocations`); GDPR-style anonymisation (`POST /api/admin/users/{user_id}/anonymize`) that retains `user_id` so foreign-key audit trails survive |
| System status | Aggregate counters: per-table row counts, role distribution, match-status distribution, connection-pool stats |
| Fake-data seed | Triggers the seed generator and displays progress |
| Task status | Polls Huey for the status of any dispatched background task |

---

## 6. Database Design

The authoritative database schema reference — including the full ER diagram, type rationale, index list, constraints, triggers, and materialised views — lives in [`docs/database-schema.md`](database-schema.md). This section summarises the layout for orientation.

### 6.1 Table Inventory

19 tables and 2 materialised views on PostgreSQL 16.

| Domain | Tables | Count |
|---|---|---|
| Identity & Authorization | `users`, `tutors`, `students`, `refresh_token_blacklist`, `password_history` | 5 |
| Teaching Catalog | `subjects`, `tutor_subjects`, `tutor_availability` | 3 |
| Messaging | `conversations`, `messages` | 2 |
| Matching & Contracts | `matches` | 1 |
| Teaching Records | `sessions`, `session_edit_logs`, `exams` | 3 |
| Reviews & Ratings | `reviews` | 1 |
| Infrastructure | `rate_limit_hits`, `audit_log`, `idempotency_keys`, `user_token_revocations` | 4 |

Materialised views: `v_tutor_active_students` (active matches per tutor for the capacity check), `v_review_stats` (aggregated rating averages per tutor).

### 6.2 Table Field Reference

The tables below show columns relevant to application-level logic. For the complete schema with full type and index detail consult `database-schema.md`.

#### 6.2.1 `users`

| Column | Type | Constraint | Description |
|---|---|---|---|
| user_id | SERIAL | PK | Surrogate key |
| username | VARCHAR(100) | UNIQUE, NOT NULL | Login identifier |
| password_hash | VARCHAR(255) | NOT NULL | bcrypt hash |
| role | VARCHAR(10) | NOT NULL, CHECK in (`tutor`,`parent`,`admin`) | Account role |
| display_name | VARCHAR(100) | NOT NULL | Display name |
| phone | VARCHAR(20) | | Contact phone |
| email | VARCHAR(100) | | Email address |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | Account creation |

#### 6.2.2 `tutors`

| Column | Type | Constraint | Description |
|---|---|---|---|
| tutor_id | SERIAL | PK | Surrogate key |
| user_id | INTEGER | FK → users, UNIQUE | One-to-one with account |
| university | VARCHAR(50) | | University |
| department | VARCHAR(50) | | Department |
| grade_year | SMALLINT | | Academic year |
| self_intro | TEXT | | Self-introduction |
| teaching_experience | TEXT | | Teaching background |
| max_students | SMALLINT | NOT NULL DEFAULT 5 | Capacity cap |
| show_university | BOOLEAN | NOT NULL DEFAULT TRUE | Visibility flag |
| show_department | BOOLEAN | NOT NULL DEFAULT TRUE | Visibility flag |
| show_grade_year | BOOLEAN | NOT NULL DEFAULT TRUE | Visibility flag |
| show_hourly_rate | BOOLEAN | NOT NULL DEFAULT TRUE | Visibility flag |
| show_subjects | BOOLEAN | NOT NULL DEFAULT TRUE | Visibility flag |

#### 6.2.3 `students`

| Column | Type | Constraint | Description |
|---|---|---|---|
| student_id | SERIAL | PK | Surrogate key |
| parent_user_id | INTEGER | FK → users, NOT NULL | Owning parent |
| name | VARCHAR(50) | NOT NULL | Student name |
| school | VARCHAR(50) | | Current school |
| grade | VARCHAR(20) | | Grade |
| target_school | VARCHAR(50) | | Target school |
| parent_phone | VARCHAR(20) | | Contact phone |
| notes | TEXT | | Free-text notes |

A parent may register at most 20 students.

#### 6.2.4 `subjects`

| Column | Type | Constraint | Description |
|---|---|---|---|
| subject_id | SERIAL | PK | Surrogate key |
| subject_name | VARCHAR(30) | UNIQUE, NOT NULL | Subject name |
| category | VARCHAR(30) | NOT NULL | `math` / `science` / `lang` / `other` |

Seeded on first startup; the `GET /api/subjects` endpoint is unauthenticated.

#### 6.2.5 `tutor_subjects`

| Column | Type | Constraint | Description |
|---|---|---|---|
| tutor_id | INTEGER | FK → tutors, composite PK | Tutor |
| subject_id | INTEGER | FK → subjects, composite PK | Subject |
| hourly_rate | NUMERIC(10,2) | NOT NULL | Per-subject hourly rate |

#### 6.2.6 `tutor_availability`

| Column | Type | Constraint | Description |
|---|---|---|---|
| availability_id | SERIAL | PK | Surrogate key |
| tutor_id | INTEGER | FK → tutors, NOT NULL | Tutor |
| day_of_week | SMALLINT | NOT NULL, CHECK BETWEEN 1 AND 7 | 1 = Monday … 7 = Sunday |
| start_time | TIME | NOT NULL | Slot start |
| end_time | TIME | NOT NULL | Slot end |

#### 6.2.7 `conversations`

| Column | Type | Constraint | Description |
|---|---|---|---|
| conversation_id | SERIAL | PK | Surrogate key |
| user_a_id | INTEGER | FK → users, NOT NULL | Lower-ID participant |
| user_b_id | INTEGER | FK → users, NOT NULL | Higher-ID participant |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | Created |
| last_message_at | TIMESTAMPTZ | | Sort key for the conversation list |

A `BEFORE INSERT/UPDATE` trigger (`fn_conversations_order_pair`) swaps the two user IDs if reversed; a unique index on `(user_a_id, user_b_id)` then enforces single-thread-per-pair without callers having to know the canonical order.

#### 6.2.8 `messages`

| Column | Type | Constraint | Description |
|---|---|---|---|
| message_id | SERIAL | PK | Surrogate key |
| conversation_id | INTEGER | FK → conversations, NOT NULL | Owning conversation |
| sender_user_id | INTEGER | FK → users, NOT NULL | Sender |
| content | TEXT | NOT NULL | Plain text |
| sent_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | Send time |

#### 6.2.9 `matches`

| Column | Type | Constraint | Description |
|---|---|---|---|
| match_id | SERIAL | PK | Surrogate key |
| tutor_id | INTEGER | FK → tutors, NOT NULL | Tutor |
| student_id | INTEGER | FK → students, NOT NULL | Student |
| subject_id | INTEGER | FK → subjects, NOT NULL | Subject |
| parent_user_id | INTEGER | FK → users, NOT NULL | Owning parent (denormalised for permission checks) |
| status | VARCHAR(15) | NOT NULL DEFAULT `pending` | One of pending / trial / active / paused / terminating / ended / cancelled / rejected |
| invite_message | TEXT | | Invitation message |
| want_trial | BOOLEAN | NOT NULL DEFAULT FALSE | If true, `accept` lands in `trial` |
| hourly_rate | NUMERIC(10,2) | | Contracted rate |
| sessions_per_week | SMALLINT | | Contracted cadence |
| start_date | DATE | | Engagement start |
| end_date | DATE | | Engagement end |
| penalty_amount | NUMERIC(10,2) | | Early-termination penalty |
| trial_price | NUMERIC(10,2) | | Trial-session price |
| trial_count | SMALLINT | | Agreed trial count |
| contract_notes | TEXT | | Addenda |
| terminated_by | INTEGER | FK → users | The user who initiated termination |
| termination_reason | TEXT | | Reason for termination |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | Created |
| updated_at | TIMESTAMPTZ | NOT NULL | Last status change |

#### 6.2.10 `sessions`

| Column | Type | Constraint | Description |
|---|---|---|---|
| session_id | SERIAL | PK | Surrogate key |
| match_id | INTEGER | FK → matches, NOT NULL | Owning match |
| session_date | DATE | NOT NULL | Lesson date |
| hours | NUMERIC(4,2) | NOT NULL | Lesson duration |
| content_summary | TEXT | NOT NULL | Lesson content |
| homework | TEXT | | Homework |
| student_performance | TEXT | | Observation |
| next_plan | TEXT | | Plan |
| visible_to_parent | BOOLEAN | NOT NULL DEFAULT FALSE | Parent visibility |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | Created |
| updated_at | TIMESTAMPTZ | NOT NULL | Last edit |

#### 6.2.11 `session_edit_logs`

| Column | Type | Constraint | Description |
|---|---|---|---|
| log_id | SERIAL | PK | Surrogate key |
| session_id | INTEGER | FK → sessions, NOT NULL | Owning session |
| field_name | VARCHAR(50) | NOT NULL | Edited field |
| old_value | TEXT | | Value before |
| new_value | TEXT | | Value after |
| edited_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | Edit time |

#### 6.2.12 `exams`

| Column | Type | Constraint | Description |
|---|---|---|---|
| exam_id | SERIAL | PK | Surrogate key |
| student_id | INTEGER | FK → students, NOT NULL | Student |
| subject_id | INTEGER | FK → subjects, NOT NULL | Subject |
| added_by_user_id | INTEGER | FK → users, NOT NULL | Author |
| exam_date | DATE | NOT NULL | Exam date |
| exam_type | VARCHAR(20) | NOT NULL | 段考 / 小考 / 模擬考 / 其他 |
| score | NUMERIC(5,2) | NOT NULL | Score |
| visible_to_parent | BOOLEAN | NOT NULL DEFAULT FALSE | Visibility |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | Created |

#### 6.2.13 `reviews`

| Column | Type | Constraint | Description |
|---|---|---|---|
| review_id | SERIAL | PK | Surrogate key |
| match_id | INTEGER | FK → matches, NOT NULL | Owning match |
| reviewer_user_id | INTEGER | FK → users, NOT NULL | Author |
| review_type | VARCHAR(20) | NOT NULL | `parent_to_tutor` / `tutor_to_student` / `tutor_to_parent` |
| rating_1 | SMALLINT | NOT NULL, 1–5 | Dimension 1 |
| rating_2 | SMALLINT | NOT NULL, 1–5 | Dimension 2 |
| rating_3 | SMALLINT | 1–5 | Dimension 3 (nullable) |
| rating_4 | SMALLINT | 1–5 | Dimension 4 (nullable) |
| personality_comment | TEXT | | Personality note |
| comment | TEXT | | Overall comment |
| is_locked | BOOLEAN | NOT NULL DEFAULT FALSE | Set by the scheduled lock task |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | Created |
| updated_at | TIMESTAMPTZ | | Last edit |

Unique index on `(match_id, reviewer_user_id, review_type)` enforces single-review-per-direction-per-match.

#### 6.2.14 `password_history`

Stores up to five most recent bcrypt hashes per user; consulted at password change to reject reuse.

| Column | Type | Constraint | Description |
|---|---|---|---|
| history_id | SERIAL | PK | Surrogate key |
| user_id | INTEGER | FK → users ON DELETE CASCADE, NOT NULL | Owning account |
| password_hash | VARCHAR(255) | NOT NULL | bcrypt hash |
| changed_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | Change time |

Backend-only; not exposed via any API endpoint.

#### 6.2.15 Infrastructure Tables

| Table | Purpose |
|---|---|
| `rate_limit_hits` | Per-bucket hit counters (`BIGSERIAL` id); pruned daily at 03:45 by `cleanup_rate_limit_hits` |
| `audit_log` | Privileged-action audit trail (`BIGSERIAL` id); `actor_user_id ON DELETE SET NULL` so records survive account removal; `resource_id` is a soft reference without an FK so records survive row deletion |
| `idempotency_keys` | DB-backed dedup store for match creation |
| `user_token_revocations` | Per-user "revoke all refresh tokens" watermark; set on admin-forced password reset |
| `refresh_token_blacklist` | Revoked JWT refresh tokens by JTI (`VARCHAR(64)` PK); pruned daily at 03:30 |

### 6.3 Relationship Summary

```
users ──1:1──→ tutors                           account extension
users ──1:N──→ students                         parent's children
users ──1:N──→ password_history                 last five hashes per user
tutors ──M:N──→ subjects   (via tutor_subjects, with per-subject rate)
tutors ──1:N──→ tutor_availability              weekly slots
users ──M:N──→ users       (via conversations, canonical pair ordering)
conversations ──1:N──→ messages
tutors ──1:N──→ matches
students ──1:N──→ matches
subjects ──1:N──→ matches
matches ──1:N──→ sessions
sessions ──1:N──→ session_edit_logs
matches ──1:N──→ reviews
students ──1:N──→ exams
```

---

## 7. API Specification

All endpoints live under `/api`. The unified envelope (§3.2) applies to every response. When `DEBUG=true` and `ENABLE_DOCS=true` the FastAPI auto-generated Swagger UI is served at `/docs`; in production both flags are off and the schema endpoints are suppressed.

Status codes follow REST conventions: 200, 201, 204, 400, 401, 403, 404, 409, 422, 429, 500.

### 7.1 Auth (`/api/auth`)

| Method | Path | Description | Authorization |
|---|---|---|---|
| POST | `/api/auth/register` | Create a parent or tutor account | Public |
| POST | `/api/auth/login` | Authenticate; sets `access_token`, `refresh_token`, `csrf_token` cookies | Public |
| POST | `/api/auth/refresh` | Issue a new access token from the refresh cookie | Refresh-cookie holder |
| POST | `/api/auth/logout` | Invalidate the refresh token (JTI added to blacklist) | Authenticated |
| GET | `/api/auth/me` | Return the authenticated user | Authenticated |
| PUT | `/api/auth/me` | Update display name, phone, email | Authenticated |
| PUT | `/api/password` | Change password (requires current password) | Authenticated |

Rate limit: login is capped at 5 attempts per 15 minutes per (IP, username) bucket.

### 7.2 Tutors (`/api/tutors`)

| Method | Path | Description | Authorization |
|---|---|---|---|
| GET | `/api/tutors/me` | Get the authenticated tutor's full profile (subjects + availability) | Tutor (self) |
| GET | `/api/tutors` | Search tutors | Parent or admin |
| GET | `/api/tutors/{id}` | Tutor detail with averages, capacity, availability | Authenticated |
| GET | `/api/tutors/{id}/reviews` | Paginated review list for a tutor | Authenticated |
| PUT | `/api/tutors/profile` | Update basic profile (university, bio, `max_students`, etc.) | Tutor (self) |
| PUT | `/api/tutors/profile/subjects` | Replace teachable subjects and per-subject rates | Tutor (self) |
| PUT | `/api/tutors/profile/availability` | Replace weekly availability | Tutor (self) |
| PUT | `/api/tutors/profile/visibility` | Update per-field visibility flags | Tutor (self) |

**Query parameters for `GET /api/tutors`:**

| Parameter | Type | Description |
|---|---|---|
| `subject_id` | int | Filter to tutors teaching this subject |
| `min_rate` / `max_rate` | float | Hourly rate range |
| `min_rating` | float | Minimum average rating |
| `school` | string | Substring match on university |
| `sort_by` | string | `rating` / `rate_asc` / `newest` |
| `page` / `page_size` | int | Default `page=1`, `page_size=20`, max 100 |

### 7.3 Students (`/api/students`)

| Method | Path | Description | Authorization |
|---|---|---|---|
| GET | `/api/students` | List the parent's own students, or students of matches the tutor is in | Parent or tutor |
| POST | `/api/students` | Register a new child (max 20 per parent) | Parent |
| PUT | `/api/students/{id}` | Update the student | Owning parent |
| DELETE | `/api/students/{id}` | Remove the student | Owning parent |

### 7.4 Subjects (`/api/subjects`)

| Method | Path | Description | Authorization |
|---|---|---|---|
| GET | `/api/subjects` | Return the seeded subject catalogue | Public |

### 7.5 Messages (`/api/messages`)

| Method | Path | Description | Authorization |
|---|---|---|---|
| GET | `/api/messages/conversations` | List the user's conversations | Authenticated |
| POST | `/api/messages/conversations` | Open a conversation (idempotent: returns the existing one if any) | Authenticated |
| GET | `/api/messages/conversations/{id}` | Paginated message stream; `before_id` cursor, limit 1–500 | Conversation participant |
| POST | `/api/messages/conversations/{id}/messages` | Send a message | Conversation participant |

Rate limits: 30 messages per conversation per minute, 100 messages per user per hour globally.

### 7.6 Matches (`/api/matches`)

| Method | Path | Description | Authorization |
|---|---|---|---|
| POST | `/api/matches` | Send an invitation (consumes `Idempotency-Key`) | Parent |
| GET | `/api/matches` | List matches; filterable by `status`, paginated | Authenticated |
| GET | `/api/matches/{id}` | Full match detail | Match participant |
| PATCH | `/api/matches/{id}/status` | Drive a state-machine transition | Per transition table (§5.4) |

**`PATCH /api/matches/{id}/status` body:**

```json
{
  "action": "accept | reject | cancel | confirm_trial | reject_trial | pause | resume | terminate | agree_terminate | disagree_terminate",
  "reason": "termination reason (required only for terminate)"
}
```

Rate limit on invitations: 10 per (tutor, parent) pair per hour.

### 7.7 Sessions

| Method | Path | Description | Authorization |
|---|---|---|---|
| GET | `/api/matches/{match_id}/sessions` | List sessions for a match (filtered for parents by `visible_to_parent`) | Match participant |
| POST | `/api/matches/{match_id}/sessions` | Log a new session | Tutor of the match |
| PUT | `/api/sessions/{id}` | Edit a session (auto-creates edit log rows) | Tutor of the match |
| GET | `/api/sessions/{id}/edit-logs` | View the edit history | Match participant |

Rate limit: 10 session creations per match per minute.

### 7.8 Exams

| Method | Path | Description | Authorization |
|---|---|---|---|
| GET | `/api/students/{student_id}/exams` | List exams (filtered by visibility) | Match participant |
| POST | `/api/students/{student_id}/exams` | Add an exam record | Parent of the student or tutor with an active match |
| PUT | `/api/exams/{id}` | Update the exam record | Author |
| DELETE | `/api/exams/{id}` | Delete the exam record | Author |

Rate limit: 20 exam writes per (student, user) per minute.

### 7.9 Reviews

| Method | Path | Description | Authorization |
|---|---|---|---|
| POST | `/api/matches/{match_id}/reviews` | Create a review (match must be `ended`) | Match participant per direction |
| GET | `/api/matches/{match_id}/reviews` | List all reviews for a match | Match participant or admin |
| PATCH | `/api/reviews/{id}` | Edit (rejected after `REVIEW_LOCK_DAYS`) | Author |
| GET | `/api/tutors/{tutor_id}/reviews` | List a tutor's reviews | Authenticated |

### 7.10 Stats (`/api/stats`)

| Method | Path | Description | Authorization |
|---|---|---|---|
| GET | `/api/stats/income` | Dispatch tutor income aggregation; returns `task_id` | Tutor |
| GET | `/api/stats/expense` | Dispatch parent expense aggregation; returns `task_id` | Parent |
| GET | `/api/stats/student-progress/{student_id}` | Synchronous exam-trend response | Student's parent, tutor with an active match, or admin |
| GET | `/api/stats/tasks/{task_id}` | Poll the status of a stats task | Authenticated |

**Query parameters:**

| Parameter | Endpoints | Description |
|---|---|---|
| `month` | income, expense | `YYYY-MM`, defaults to current month |

### 7.11 Admin (`/api/admin`)

All admin endpoints require `role = admin`.

| Method | Path | Description |
|---|---|---|
| GET | `/api/admin/tables` | List tables and the import/export allow-list |
| GET | `/api/admin/users` | List all accounts |
| GET | `/api/admin/system-status` | Per-table counts, role distribution, match-status distribution, pool stats |
| POST | `/api/admin/export/{table_name}` | Export a single table as CSV |
| POST | `/api/admin/import/{table_name}` | Import a CSV (`?upsert=true` for upsert mode) |
| POST | `/api/admin/export-all` | Export all exportable tables as a ZIP |
| POST | `/api/admin/import-all` | Import a ZIP (`?clear_first=true&upsert=true`) |
| POST | `/api/admin/seed` | Trigger fake-data generation |
| POST | `/api/admin/reset` | Step 1 of database reset: issue a reset token (5-minute TTL) |
| POST | `/api/admin/reset/confirm` | Step 2: redeem the token + password to truncate, after automatic backup |
| POST | `/api/admin/users/{user_id}/anonymize` | GDPR anonymisation (keeps `user_id` for FK audit) |
| POST | `/api/admin/users/{user_id}/reset-password` | Force password reset; revokes all refresh tokens for the user |
| GET | `/api/admin/tasks/{task_id}` | Poll admin background task status |

**Database reset flow:** Step 1 calls `/reset` to obtain a `reset_token`; Step 2 calls `/reset/confirm` within 5 minutes with the token and the admin's password. The system backs up everything (including `users`) to the local filesystem before truncating. Each admin account is rate-limited to one reset per 7 days.

### 7.12 Health (`/health`)

| Method | Path | Description | Authorization |
|---|---|---|---|
| GET | `/health` | Liveness + DB ping for the container healthcheck | Public |

### 7.13 Cross-Cutting Middleware

The middleware stack, from outermost to innermost in the request flow:

| Order | Middleware | Behaviour |
|---|---|---|
| 1 | CORS | Origin allow-list from `CORS_ORIGINS`; `allow_credentials=True` |
| 2 | RequestID | Injects `X-Request-ID` (request and response); included in every log line |
| 3 | BodySizeLimit | Rejects oversized bodies before the handler reads them (default 50 MB) |
| 4 | SecurityHeaders | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Strict-Transport-Security`, conservative CSP |
| 5 | AccessLog | Structured JSON access log entries |
| 6 | UserConcurrencyQuota | Caps simultaneous in-flight requests per authenticated user (default 5); returns 429 with `Retry-After: 1` |
| 7 | CSRF | Double-submit `X-CSRF-Token` against `csrf_token` cookie on mutating methods; rejected before the rate limiter so an attacker can't drain a victim's bucket |
| 8 | RateLimit | Per-path and per-user buckets, backed by `rate_limit_hits` so workers share counters |

Nginx in front of the API also applies an edge-level `limit_req_zone` (20 r/s, burst 40) and a global CSP.

---

## 8. Frontend Routes and Components

### 8.1 Route Table

```
/login                              → LoginView           (guest only)
/register                           → RegisterView        (guest only)

# Shared (parent or tutor, not admin)
/messages                           → ConversationListView
/messages/:id                       → ChatView

# Parent (role: parent)
/parent                             → ParentDashboardView
/parent/search                      → SearchView
/parent/tutor/:id                   → TutorDetailView
/parent/students                    → StudentsView
/parent/match/:id                   → MatchDetailView
/parent/expense                     → ExpenseView
/parent/profile                     → ProfileView

# Tutor (role: tutor)
/tutor                              → TutorDashboardView
/tutor/profile                      → ProfileView
/tutor/match/:id                    → MatchDetailView
/tutor/income                       → IncomeView

# Admin (role: admin)
/admin                              → AdminDashboardView

# Defaults
/                                   → Redirect to role-specific home
/:pathMatch(.*)*                    → NotFoundView
```

Guarded routes call `auth.ensureVerified()` to re-confirm role from the server on every navigation. `localStorage.user` is a cache only; the server is authoritative. Unverified cache contents never influence role checks, so a tampered client cannot escalate privilege.

### 8.2 Pinia Stores

| Store | Responsibility |
|---|---|
| `stores/auth.js` | Authenticated user, role, `ensureVerified()`, token-refresh orchestration |
| `stores/tutor.js` | Tutor search results cache and current filters |
| `stores/notifications.js` | User-scoped notification queue (localStorage-backed) |
| `stores/toast.js` | Transient toast messages |

### 8.3 Key Components

| Component | Used In |
|---|---|
| `common/AppNav.vue` | All authenticated views |
| `common/StatusBadge.vue` | Dashboards, MatchDetailView |
| `common/StatCard.vue` | Dashboards, IncomeView, ExpenseView |
| `common/ConfirmDialog.vue` | Destructive actions |
| `tutor/TutorCard.vue` | SearchView |
| `tutor/TutorFilter.vue` | SearchView |
| `tutor/AvailabilityCalendar.vue` | TutorDetailView, tutor ProfileView |
| `match/ContractForm.vue` | MatchDetailView |
| `match/ContractConfirmModal.vue` | MatchDetailView (accept-with-trial flow) |
| `match/InviteForm.vue` | TutorDetailView |
| `session/SessionForm.vue` | MatchDetailView |
| `session/SessionTimeline.vue` | MatchDetailView |
| `review/RadarChart.vue` | TutorDetailView |
| `review/ReviewList.vue` | TutorDetailView, MatchDetailView |
| `stats/IncomeChart.vue` | IncomeView |
| `stats/ExpenseChart.vue` | ExpenseView |
| `stats/ProgressChart.vue` | MatchDetailView |

---

## 9. Asynchronous Task Engine

### 9.1 Architecture

The worker runs as a dedicated container (`docker-compose.yml` service `worker`) using `SqliteHuey` with a custom JSON serialiser (the default pickle serialiser is unsafe for cross-process use). The queue file `data/huey.db` lives on a Docker volume shared with the API container so both processes see the same queue state. Tasks open their own psycopg2 connections to the same PostgreSQL database the API uses.

### 9.2 Task Inventory

Among the tasks listed below, the stats tasks and the scheduled tasks are genuinely asynchronous (dispatched to the worker). The import/export and seed tasks have Huey task definitions in the codebase but the current admin routes execute them synchronously inside the request handler.

| Task | Trigger | Description |
|---|---|---|
| `calculate_income_stats(user_id, month?)` | `GET /api/stats/income` | Aggregate tutor earnings; 3 retries with 10 s backoff |
| `calculate_expense_stats(user_id, month?)` | `GET /api/stats/expense` | Aggregate parent expense; 3 retries with 10 s backoff |
| `lock_expired_reviews` | Cron, daily 03:00 UTC | Sets `is_locked=true` on reviews older than `REVIEW_LOCK_DAYS`; protected by a task lock so concurrent runs are skipped |
| `cleanup_refresh_token_blacklist` | Cron, daily 03:30 UTC | Prunes rows past `expiry_at` |
| `cleanup_rate_limit_hits` | Cron, daily 03:45 UTC | Prunes expired rate-limit buckets |
| `import_csv_task` | Task definition only | Admin routes currently import synchronously |
| `export_csv_task` | Task definition only | Admin routes currently export synchronously |
| `generate_seed_data` | Task definition only | Admin `/seed` currently runs synchronously |

### 9.3 Task-Status Polling

Asynchronous endpoints return a `task_id` immediately. The frontend polls `GET /api/stats/tasks/{task_id}` (stats) or `GET /api/admin/tasks/{task_id}` (admin). Response:

```json
{
  "success": true,
  "data": {
    "task_id": "abc123",
    "status": "pending | running | completed | failed",
    "result": { "...": "..." },
    "error": null
  }
}
```

### 9.4 Worker Module Layout

```python
# app/worker.py
from huey import SqliteHuey
from app.shared.infrastructure.config import settings
from app.shared.infrastructure.huey_json_serializer import JSONSerializer

huey = SqliteHuey(filename=settings.huey_db_path, serializer=JSONSerializer())

from app.tasks import scheduled       # noqa: cron-scheduled maintenance tasks
from app.tasks import stats_tasks     # noqa: calculate_income_stats, calculate_expense_stats
from app.tasks import import_export   # noqa: task defs (admin routes run sync today)
from app.tasks import seed_tasks      # noqa: task def (admin route runs sync today)
```

`app/tasks/` modules in summary:

- **`scheduled.py`** — `lock_expired_reviews` (daily 03:00 UTC), `cleanup_refresh_token_blacklist` (03:30), `cleanup_rate_limit_hits` (03:45). Cron-only; never triggered by API routes.
- **`stats_tasks.py`** — `calculate_income_stats`, `calculate_expense_stats`. Dispatched by the analytics routes; results polled by the frontend.
- **`import_export.py`** — Huey definitions for `import_csv_task` / `export_csv_task`; not currently dispatched by the admin routes.
- **`seed_tasks.py`** — Huey definition for `generate_seed_data`; not currently dispatched by the admin `/seed` route.

---

## 10. Team Responsibilities

### 10.1 Team Composition

| Member | Background | Role |
|---|---|---|
| **A (Tech Lead)** | Full-stack development | System architecture and core implementation |
| **B** | Basic web | Frontend implementation |
| **C** | Basic web | Frontend implementation + system testing |
| **D** | Learning relational databases | Schema build-out + presentation slides |
| **E** | Learning relational databases | Schema build-out + written report |

### 10.2 Member Responsibilities

| Member | Scope | Deliverables |
|---|---|---|
| **A** | Backend architecture (FastAPI, bounded contexts, repositories, JWT auth, middleware stack), Huey worker, complex frontend pages (match state machine, review radar chart, stats charts), fake-data generator, code review, technical guidance | Backend source, core frontend pages, Docker compose stack, `start.bat` |
| **B** | Frontend: login/register pages, parent dashboard, search page, tutor card, messaging UI | Owned Vue views and components |
| **C** | Frontend: tutor dashboard, tutor profile editor, session log form/timeline, exam record page; integration testing | Owned Vue views and components, test notes |
| **D** | Schema build-out (~half the tables) in both the Access prototype and the PostgreSQL DDL; presentation slides and oral delivery | `.accdb` prototype, schema DDL contributions, PowerPoint deck |
| **E** | Schema build-out (the other ~half of the tables); written report (system description, screenshots, user manual) | `.accdb` prototype, schema DDL contributions, written report |
| **All** | Demo rehearsals; demo-script design | Demo script |

### 10.3 Weekly Cadence

| Week | A (Tech Lead) | B, C (Frontend) | D, E (Database + Docs) |
|:---:|---|---|---|
| **1** | Backend skeleton, identity context, Huey init, frontend project init, Docker compose v1 | Familiarise with Vue dev environment, run sample pages, practise Axios calls | Build the 13 business tables in Access; mirror in the PostgreSQL DDL inside `init_db.py`; hand the schema to A for verification |
| **2** | Core APIs (tutor search, student CRUD, match state machine, messaging) | B: login/register, search, tutor card; C: tutor dashboard, profile editor | Use the admin console to load seed data; validate the schema against actual queries; start outlining the slides |
| **3** | Teaching-management APIs (session, exam), admin console APIs, middleware hardening | B: parent dashboard, messaging UI; C: session log form/timeline, exam page | Walk the demo script and capture screenshots; first draft of the written report |
| **4** | Review system, statistics, CSV import/export, fake-data generator | B: match detail (invite form, contract form); C: review form, integration testing | Finalise the slides; finish the written report (including screenshots and user manual) |
| **5** | End-to-end bug fixes, UI polish | Assist with frontend bug fixes, final UI tweaks | Full-team demo rehearsals; spare-scenario preparation |

### 10.4 Frontend Member Guidance (B, C)

The pages owned by B and C do not require backend changes. The workflow is:

1. **Layout** — assemble the page from Vue components per the agreed design.
2. **API calls** — use the wrapped functions in `src/api/` (already prepared by A).
3. **Data binding** — render the response into the page.
4. **Form submission** — push user input through the matching API function.

The project skeleton (router, Pinia stores, Axios wrapper) and per-resource API modules are prepared in advance so B and C focus on UI work.

### 10.5 Database Member Guidance (D, E)

D and E do not need to write application code. The deliverables are:

1. **Schema build-out** — work through §6.2 in both the Access prototype (course requirement) and the PostgreSQL DDL inside `app/init_db.py` (running system).
2. **Relationship diagram** — draw the relationships in Access's relationship view (slide material).
3. **Suggested split** — D owns `users`, `tutors`, `students`, `subjects`, `tutor_subjects`, `tutor_availability`, `conversations` (7 tables); E owns `messages`, `matches`, `sessions`, `session_edit_logs`, `exams`, `reviews` plus the support tables (6+ tables).
4. **Verification** — A reviews the PostgreSQL DDL and runs end-to-end queries against the live database to confirm names and types match the API expectations.

---

## 11. Development Schedule

Five-week cycle.

### Week 1 — Foundation

- [ ] Build the 13 business tables in the Access prototype and mirror them in the PostgreSQL DDL (`init_db.py`)
- [ ] Initialise the backend repository: FastAPI scaffolding, psycopg2 pool, `Settings`, structured logging
- [ ] Implement the shared kernel (base repository, exception hierarchy, response envelope)
- [ ] Complete the identity context: register, login, refresh, logout, admin bootstrap
- [ ] Initialise the Huey worker and verify task dispatch
- [ ] Initialise the frontend repository: Vue + Router + Pinia + Axios wrapper
- [ ] Build the login page and the navigation guard
- [ ] Stand up the Docker compose stack (`db`, `api`, `worker`, `web`) and `start.bat`

### Week 2 — Core Business Flows

- [ ] Catalog context: tutor and student repositories plus pages
- [ ] Tutor search (filters, sort, card list, detail page)
- [ ] Tutor profile editor (basic, availability, visibility)
- [ ] Matching context: full state-machine API and tests, idempotency, per-pair rate limit
- [ ] Messaging context: conversation creation, message paging, rate limits

### Week 3 — Teaching Management

- [ ] Teaching context: session logs (with `visible_to_parent` and the edit-log trigger)
- [ ] Teaching context: exam records with the visibility rule
- [ ] Tutor and parent dashboards
- [ ] Admin console skeleton

### Week 4 — Reviews, Statistics, Bulk Operations

- [ ] Review context: three-way form, radar chart, 7-day lock
- [ ] Analytics context: Huey-based income and expense; synchronous student-progress
- [ ] CSV import/export (admin synchronous routes)
- [ ] Fake-data generator and the `/seed` route
- [ ] Complete the admin console (import/export, reset two-step flow, system status)

### Week 5 — Hardening and Delivery

- [ ] End-to-end testing
- [ ] UI polish
- [ ] Slides, screenshots, written report
- [ ] Full-team demo rehearsals

---

## 12. Demonstration Flow

Total target: 10–15 minutes.

### 12.1 Architecture Walkthrough (2 min)

1. Open the Swagger UI (`http://localhost:8000/docs`, with `DEBUG=true` and `ENABLE_DOCS=true`) to show the full endpoint catalogue and interactive testing surface.
2. Open the Access prototype (`docs/tutoring.accdb`) and show the relationship diagram — the course-required artefact.
3. Walk through the architecture diagram (§2.1): Nginx → FastAPI → PostgreSQL, with the Huey worker on the side.

### 12.2 Admin Operations (2 min)

1. Log in as admin and open the admin console.
2. Show the system-status panel.
3. Click "seed data" and explain that the UI stays responsive while the data is generated.
4. After generation, show that the dataset is now visible across the system.

### 12.3 Parent Flow (4 min)

1. Register and log in as a parent.
2. Add a child.
3. Open the search page; filter by subject, hourly rate, and rating.
4. Click a tutor card and review the radar chart and availability.
5. Use "Send message" to open a conversation.
6. Use "Send invitation" with a trial period and an invitation message.

### 12.4 Tutor Flow (4 min)

1. Log in as the tutor; the dashboard surfaces the new invitation.
2. Open the invitation, accept it, and enter the trial phase.
3. Confirm the trial; the match moves to `active`.
4. Log a session marked visible to the parent.
5. Log an exam record.

### 12.5 Reviews and Statistics (2 min)

1. End the match and have the parent write the parent→tutor review.
2. Have the tutor write the tutor→student and tutor→parent reviews.
3. Show the tutor income chart (toggle month/student/subject groupings).
4. Show the parent expense chart.
5. Show the student progress line chart.

### 12.6 Closing (1 min)

1. From the admin console, trigger a one-click export-all (ZIP).
2. Open the Access prototype to compare schema with the live PostgreSQL data.
3. Issue a request against a specific endpoint in Swagger UI to show the JSON envelope.

---

## 13. Appendix

### 13.1 Optional Extensions

Not in the base scope; consider only if schedule permits.

| Feature | Notes |
|---|---|
| Access reporting | Add a monthly-income report inside the Access prototype to showcase Access's reporting features |
| Profile photos | Tutor profile photo upload |
| Read receipts | Add read markers and unread counters to the messaging system |
| Real-time notifications | Dashboard push for new invitations, messages, and status changes |
| Dark mode | Frontend dark theme |
| Calendar view | Session logs rendered on a calendar |

### 13.2 Known Limitations

| Limitation | Detail |
|---|---|
| Non-realtime messaging | Polling-based; no WebSocket push |
| Not internet-ready as shipped | The compose stack is suitable for classroom demos and development; production deployment requires TLS termination in front of the web container, rotated secrets, a backup policy, and DB connection-pool sizing under load |
| Single node | One instance of each service; the API is designed so rate-limit and token-blacklist state are shared in the database, but horizontal scaling has not been exercised |
| Import/export is synchronous | The Huey task definitions exist but the admin routes run import and export synchronously inside the request handler |

### 13.3 Production Deployment Notes

The `web` container listens on plain HTTP port 8080 because the official `nginx-unprivileged` image cannot bind 443 without extra capabilities. In production:

- Terminate TLS in front of the container (Caddy, Traefik, an AWS ALB, Cloudflare, etc.). Pointing the public address directly at port 80 will ship auth cookies in cleartext and silently neuter the HSTS header.
- Set `COOKIE_SECURE=true` so auth cookies carry the `Secure` attribute. The default is `false` to keep local `docker compose up` usable without a TLS cert.
- Point the TLS proxy at `web:8080` inside the overlay network; let it set `X-Forwarded-Proto: https`. Uvicorn runs with `--proxy-headers` and will honour the forwarded scheme when generating redirects.

The complete deployment checklist lives in `SECURITY.md`.

### 13.4 Related Documents

- **[`docs/architecture.md`](architecture.md)** — System architecture reference: C4-style diagrams, bounded-context map, frontend module map, request/auth flows, match state machine, ER view.
- **[`docs/database-schema.md`](database-schema.md)** — Complete database schema reference: table structure, relationships, constraints, materialised views, triggers, indexes.
- **`README.md`** — Quick-start, technology stack summary, repository layout, run instructions.
- **`SECURITY.md`** — Security controls, threat matrix, production-deployment checklist, token rotation procedure.

---

*End of document.*
