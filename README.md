# TMRP — Tutor Matching and Rating Platform

A full-stack web application that connects parents with private tutors. Parents search for tutors, chat in-app, send match invitations, and track their children's lesson notes and exam scores. Tutors manage students, lesson records, and earnings. After a match ends, both sides exchange structured ratings.

Built as the final group project for a university SQL course. The database was originally implemented in MS Access to meet course requirements, and has since been migrated to PostgreSQL so the system can run anywhere Docker is available.

---

## Table of Contents

- [What the System Does](#what-the-system-does)
- [Core Features](#core-features)
- [Technology Stack](#technology-stack)
- [Quick Start (Docker)](#quick-start-docker)
- [Local Development](#local-development)
- [Repository Layout](#repository-layout)
- [System Architecture](#system-architecture)
- [Database Design](#database-design)
- [API Overview](#api-overview)
- [Match Status Machine](#match-status-machine)
- [Background Tasks](#background-tasks)
- [Security & Production Hardening](#security--production-hardening)
- [Documentation](#documentation)
- [Team and Roles](#team-and-roles)
- [Known Limitations](#known-limitations)

---

## What the System Does

Think of it as a version of "104 人力銀行" scoped to private tutoring. A typical flow:

1. A parent searches for tutors by subject, hourly rate range, star rating, and school.
2. The parent reads a tutor's profile and past reviews, then starts an in-app chat.
3. The parent sends a match invitation with contract terms (rate, sessions per week, optional trial).
4. The tutor accepts, rejects, or proposes a trial.
5. During teaching, the tutor records lesson notes and exam scores; the parent watches progress.
6. When the match ends, both sides write structured reviews. Reviews lock after 7 days.

The backend enforces all business rules — the status machine, rating visibility, the review lock window, and the tutor capacity check — so the frontend only needs to render state.

---

## Core Features

**Three user roles:** Parent, Tutor, and Admin.

### For Parents
- Search tutors by subject, hourly rate range, minimum star rating, and school
- View detailed tutor profiles (bio, availability, subjects, rates, past reviews)
- Message tutors directly through in-app conversations
- Send match invitations with contract terms (hourly rate, sessions per week, optional trial period)
- Track children's lesson notes and exam scores (subject to the tutor's visibility settings)
- View monthly expense breakdowns by subject and tutor

### For Tutors
- Manage a searchable profile with granular visibility controls (hide university, major, rates, etc.)
- Receive and respond to match invitations
- Record lesson session notes (date, hours, content, homework, performance, next plan)
- Log exam scores with optional visibility to the parent
- Rate students and parents after a match ends
- View monthly income breakdowns by student and subject

### For Admins
- View all registered users
- Export and import table data as CSV (runs asynchronously in the worker)
- Generate realistic fake seed data for testing
- Inspect background task status

### Shared
- Three-way rating system: parent → tutor, tutor → student, tutor → parent
- 7-day review edit window; reviews lock automatically after that
- In-app one-on-one messaging
- Session edit history: every field change is logged with old/new values

---

## Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Frontend framework | Vue 3 | 3.5.13 |
| Build tool | Vite | 6.0.5 |
| State management | Pinia | 2.3.0 |
| Client-side routing | Vue Router | 4.5.0 |
| HTTP client | Axios | 1.7.9 |
| Charts | Chart.js + vue-chartjs | 4.5.1 / 5.3.3 |
| CSS framework | Tailwind CSS | 4.2.2 |
| Backend framework | FastAPI | 0.115.6 |
| ASGI server | Uvicorn | 0.34.0 |
| Data validation | Pydantic | 2.10.4 |
| Database driver | psycopg2 | >=2.9.11 |
| Password hashing | bcrypt | 4.2.1 |
| JWT | PyJWT | 2.9.0 |
| Task queue | huey | 2.5.2 |
| Database | PostgreSQL | 16 (alpine) |
| Reverse proxy (prod) | Nginx | 1.x (in web image) |

---

## Quick Start (Docker)

The fastest way to run the whole stack — database, API, worker, and frontend — on any machine with Docker:

```bash
# 1. Clone
git clone <this-repo-url>
cd "TMRP (Tutor Matching and Rating Platform)"

# 2. Prepare the repo-root env file (DB_USER and DB_NAME consumed by docker-compose)
cp .env.example .env
# Edit .env — set DB_USER and DB_NAME (docker compose aborts if either is empty).
# The database password is a Docker secret; set it in the next step.

# 3. Create Docker secrets (passwords and JWT key — never committed to git)
cp secrets/db_password.txt.example     secrets/db_password.txt
cp secrets/jwt_secret_key.txt.example  secrets/jwt_secret_key.txt
cp secrets/admin_password.txt.example  secrets/admin_password.txt
# Populate each file with a real value:
#   jwt_secret_key.txt  — at least 32 hex chars:
#       python -c "import secrets; print(secrets.token_hex(32))" > secrets/jwt_secret_key.txt
#   admin_password.txt  — a strong password (min 8 chars, not 'admin' or 'admin123')
#   db_password.txt     — any strong password

# 4. Prepare the backend env file (non-secret settings only)
cp tutor-platform-api/.env.docker.example tutor-platform-api/.env.docker
# Edit .env.docker — change ADMIN_USERNAME away from the placeholder default.
# JWT_SECRET_KEY and ADMIN_PASSWORD are read from secrets/ files, not from here.

# 5. Build and start
docker compose up -d --build
```

Once the containers are healthy:

| Service | URL |
|---------|-----|
| Frontend | http://localhost (host 80 → container 8080, Nginx runs non-root) |
| API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs (only when `DEBUG=true`) |
| PostgreSQL | 127.0.0.1:5433 (bound to loopback; credentials from repo-root `.env`) |

Stop and remove containers:

```bash
docker compose down          # keep data
docker compose down -v       # also wipe the database volume
```

The API container runs schema initialisation, seeds the subject catalogue, and provisions the admin account on first boot. It refuses to start if `JWT_SECRET_KEY` or `ADMIN_PASSWORD` are left at their insecure defaults.

---

## Local Development

Running without Docker is useful for active development and debugging.

**Requirements:**
- Python 3.10+
- Node.js 18+
- PostgreSQL 14+ running locally (or a reachable remote instance)

**Steps:**

1. Create a database:
   ```bash
   createdb tmrp
   # or: psql -c "CREATE DATABASE tmrp;"
   ```

2. Install backend dependencies:
   ```bash
   cd tutor-platform-api
   pip install -r requirements.txt
   cp .env.example .env
   ```
   Then edit `.env` — generate a secret with:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

3. Install frontend dependencies:
   ```bash
   cd ../tutor-platform-web
   npm install
   ```

4. Launch everything from the backend folder:
   ```bash
   cd ../tutor-platform-api
   start.bat
   ```
   This opens three terminals: the huey worker, the FastAPI server (`uvicorn --reload`), and the Vite dev server.

**Default local URLs:**

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5273 |
| API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |

---

## Repository Layout

```
project-root/
├── docker-compose.yml           # Four services: db, api, worker, web
├── .env.example                 # Repo-root env template (DB credentials for compose)
├── docs/                        # Specifications and design notes
│   ├── project-spec.md          # Full system specification (v5.1)
│   └── production-hardening-plan.md
│
├── tutor-platform-api/          # Python backend (FastAPI)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── start.bat                # Local one-click launcher (Windows)
│   ├── .env.example             # Local template
│   ├── .env.docker.example      # Container template
│   ├── app/
│   │   ├── main.py              # FastAPI app, middleware wiring, lifespan
│   │   ├── init_db.py           # Schema DDL, subject seeds, admin bootstrap
│   │   ├── worker.py            # Huey instance
│   │   ├── shared/              # Shared kernel (api/, domain/, infrastructure/)
│   │   ├── identity/            # BC: auth, users, JWT
│   │   ├── catalog/             # BC: tutors, students, subjects
│   │   ├── matching/            # BC: matches, status machine, contracts
│   │   ├── teaching/            # BC: sessions, exams, edit logs
│   │   ├── review/              # BC: three-way ratings, 7-day lock
│   │   ├── messaging/           # BC: conversations and messages
│   │   ├── analytics/           # BC: income / expense statistics
│   │   ├── admin/               # BC: CSV import-export, seed, task status
│   │   ├── middleware/          # request_id, body_size_limit, security_headers, access_log, rate_limit, user_quota
│   │   ├── tasks/               # Huey background tasks
│   │   └── utils/               # csv_handler, security, logger
│   ├── seed/                    # Fake data generator
│   ├── data/                    # huey.db and mounted volumes
│   └── tests/
│
└── tutor-platform-web/          # Vue 3 frontend
    ├── Dockerfile               # Vite build → nginx-unprivileged (listens on 8080)
    ├── nginx.conf               # /api/* → api:8000, SPA fallback, edge rate limit
    ├── vite.config.js
    ├── package.json
    ├── scripts/                 # check-no-v-html.mjs (pre-build lint guard)
    └── src/
        ├── main.js
        ├── App.vue
        ├── constants.js         # Shared enums (roles, match status, ...)
        ├── router/index.js      # Route table + role guards
        ├── stores/              # Pinia: auth, tutor, match, message, toast
        ├── api/                 # Axios services, one file per resource (+ baseURL, authHandler)
        ├── views/
        │   ├── LoginView.vue / RegisterView.vue
        │   ├── parent/          # Dashboard, Search, TutorDetail, MatchDetail, Students, Expense
        │   ├── tutor/           # Dashboard, Profile, MatchDetail, Income
        │   ├── messages/        # ConversationList, Chat
        │   └── admin/           # AdminDashboard
        ├── components/          # common, match, review, session, stats, tutor
        └── composables/         # useMatchDetail
```

---

## System Architecture

Four processes, connected by HTTP and a shared PostgreSQL database:

```
  Browser (Vue 3 SPA)
       │   HTTP / JSON (Axios)
       ▼
  Nginx (web container)      ── serves static assets, proxies /api/* ──┐
                                                                        │
  FastAPI (api container)  ◄──────────────────────────────────────────┘
       │   JWT auth, domain services, repositories
       │   middleware (outer → inner):
       │     CORS → request_id → body_size_limit → security_headers → access_log → user_quota → rate_limit
       ▼
  PostgreSQL 16 (db container, volume: pgdata)
       ▲
       │
  Huey Worker (worker container)  ── CSV import/export, seed, stats, review lock
       (SQLite queue at data/huey.db, shared volume with api)
```

The API container's `lifespan` hook initialises the connection pool, runs the schema DDL (idempotent `CREATE TABLE IF NOT EXISTS`), seeds the subject catalogue, provisions the admin user, and runs a bootstrap verification step — all before accepting requests. The Docker healthcheck uses a `start_period` of 90 s so dependent services (web) only come up once the API is ready.

---

## Database Design

16 tables on PostgreSQL 16. 13 are business tables; 3 support cross-worker auth, rate limiting, and auditing.

### Business tables

**Users and roles**

| Table | Purpose |
|-------|---------|
| users | Core account: username, password hash, role (parent/tutor/admin), display name, contact |
| tutors | Tutor profile: university, department, grade year, bio, visibility flags |
| students | Children managed by a parent: name, school, grade, target school, notes |

**Subjects and availability**

| Table | Purpose |
|-------|---------|
| subjects | Subject catalogue: name, category |
| tutor_subjects | Many-to-many: which tutors teach which subjects, at what hourly rate (composite PK) |
| tutor_availability | Weekly availability slots (day of week + time range) |

**Communication**

| Table | Purpose |
|-------|---------|
| conversations | One record per unique user pair (unique index on `(user_a_id, user_b_id)`) |
| messages | Individual messages within a conversation |

**Matching and contracts**

| Table | Purpose |
|-------|---------|
| matches | The core matching record: tutor, student, subject, contract terms, status, trial fields |

**Teaching records**

| Table | Purpose |
|-------|---------|
| sessions | Lesson records: date, hours, content, homework, performance, next plan |
| session_edit_logs | Audit trail: every field edit (field name, old value, new value) |
| exams | Exam score records with visibility flag |

**Ratings**

| Table | Purpose |
|-------|---------|
| reviews | Post-match reviews supporting three directions, with 7-day lock flag |

### Support tables

| Table | Purpose |
|-------|---------|
| refresh_token_blacklist | Revoked refresh-token JTIs; shared across API workers |
| rate_limit_hits | Hit counters for the rate-limit middleware; shared across workers |
| audit_log | Privileged-action audit trail: actor, action, resource type/ID, old/new values. `actor_user_id` uses `ON DELETE SET NULL` so records survive account removal; `resource_id` is a soft reference with no FK so records survive row deletion. |

### Key constraints

- Most primary keys are `SERIAL` (auto-incrementing integer); `rate_limit_hits` and `audit_log` use `BIGSERIAL` for high-volume inserts, and `refresh_token_blacklist` uses a `VARCHAR(64)` JTI as its primary key
- `tutor_subjects` uses a composite primary key `(tutor_id, subject_id)`
- `conversations` has a unique index on `(user_a_id, user_b_id)` to prevent duplicate threads
- `reviews` has a unique index on `(match_id, reviewer_user_id, review_type)` — one review per reviewer per match per direction
- `tutor_availability.day_of_week` is a `CHECK (day_of_week BETWEEN 0 AND 6)` constraint
- All timestamps are `TIMESTAMPTZ` with `NOW()` defaults

---

## API Overview

All endpoints return a unified response envelope:

```json
{
  "success": true,
  "data": { "...": "..." },
  "message": "optional status message"
}
```

HTTP status codes follow REST conventions: 200, 201, 400, 401, 403, 404, 409, 422, 500.

### Endpoint groups

| Prefix | Bounded Context | Responsibility |
|--------|-----------------|----------------|
| `/api/auth` | identity | Register, login, refresh, current user |
| `/api/tutors` | catalog | Search, profiles, availability, visibility |
| `/api/students` | catalog | Parent's children management |
| `/api/subjects` | catalog | Subject catalogue (public) |
| `/api/matches` | matching | Invitations, status transitions, contract details |
| `/api/sessions` | teaching | Lesson notes CRUD, edit history |
| `/api/exams` | teaching | Exam score records |
| `/api/reviews` | review | Post-match ratings (three directions) |
| `/api/messages` | messaging | Conversations and messages |
| `/api/stats` | analytics | Income (tutor) and expense (parent) breakdowns |
| `/api/admin` | admin | User management, CSV ops, seed data, task status |
| `/health` | shared | API and database liveness |

### Authentication

Protected endpoints require a JWT bearer token:

```
Authorization: Bearer <access_token>
```

Access tokens expire after `JWT_EXPIRE_MINUTES` (default **5 minutes**, hard-capped at 15 by a lifespan check) and are refreshed through the refresh-token flow. Revoked refresh tokens are recorded in `refresh_token_blacklist` so the check is consistent across API workers. `JWT_SECRET_KEY_PREVIOUS` can optionally hold the prior signing key during a rotation window so in-flight sessions don't 401. Role enforcement uses a `require_role()` dependency that returns 403 on mismatch.

### Notable design decisions

- **Tutor search** supports multi-parameter filtering (subject, rate range, star rating, school/university) with server-side pagination backed by SQL `LIMIT`/`OFFSET`.
- **Session editing** auto-creates a `session_edit_logs` entry for every changed field, recording the field name, old value, new value, and edit timestamp.
- **Review locking** is enforced by a scheduled background task (daily at 3 AM) that marks reviews older than 7 days as immutable. The `PATCH /api/reviews/{id}` endpoint also re-checks the flag before allowing edits.
- **Tutor capacity** is validated when a parent sends an invitation. The backend rejects the request if the tutor already has their maximum number of active or trial students.
- **Unified error handling**: `DomainException`s map to HTTP status, validation errors to 422 with a structured errors array, and unhandled exceptions to 500 with a `request_id` so users can report reproducible incidents.

---

## Match Status Machine

A match progresses through a defined set of states. Only specific roles can trigger each transition.

```
               [Parent sends invitation]
                          │
                       pending
                      /        \
         [Tutor accepts,    [Tutor rejects]
          no trial]             │
             │              rejected
          active
                             /
         [Tutor accepts,
          with trial]
             │
           trial
          /      \
  [Trial ok]   [Trial rejected]
      │              │
   active         rejected
      │
  [Paused by either party]
      │
   paused
      │
  [Resume]
      │
   active
      │
  [Either party initiates termination]
      │
 terminating
      │
  [Other party confirms]
      │
    ended
```

Additional state: `cancelled` (parent withdraws a pending invitation before the tutor responds).

Each `(current_status, action)` pair maps to a new status and a set of roles permitted to perform the action. The backend validates both the current status and the requesting user's role before applying any transition.

---

## Background Tasks

The huey worker runs in a separate container backed by a SQLite queue at `data/huey.db`, sharing the same volume as the API so both processes see the same queue state. Tasks connect to the same PostgreSQL database as the API.

| Task | Trigger | Description |
|------|---------|-------------|
| `import_csv_task` | Admin action | Bulk import CSV data (upsert or overwrite) |
| `export_csv_task` | Admin action | Export a table to CSV |
| `generate_seed_data` | Admin action | Populate the database with realistic fake data |
| `calculate_income_stats` | Admin / scheduled | Aggregate tutor earnings by month, student, and subject |
| `calculate_expense_stats` | Admin / scheduled | Aggregate parent spending by month and subject |
| `lock_expired_reviews` | Scheduled (03:00 daily) | Mark reviews older than 7 days as immutable |

Admin-triggered tasks return a `task_id` immediately. The frontend polls `GET /api/admin/tasks/{task_id}` for status and completion.

---

## Security & Production Hardening

The backend ships with several middleware layers (innermost → outermost):

1. **RateLimitMiddleware** — per-IP and per-user rate limits, persisted in `rate_limit_hits` so limits are consistent across API replicas.
2. **UserConcurrencyQuotaMiddleware** — caps the number of simultaneous in-flight requests a single authenticated user may hold open (default 5, configurable via `DB_PER_USER_QUOTA`). Prevents one caller from monopolising all database pool slots; returns 429 with `Retry-After: 1` when the limit is hit.
3. **AccessLogMiddleware** — structured JSON access logs, tagged with the request ID.
4. **SecurityHeadersMiddleware** — sets `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Strict-Transport-Security`, and a conservative CSP.
5. **BodySizeLimitMiddleware** — rejects oversized request bodies before the handler reads them (cap from `MAX_REQUEST_BODY_BYTES`, default 50 MB).
6. **RequestIDMiddleware** — injects an `X-Request-ID` into every request and response; propagated into logs and 500 error bodies.
7. **CORSMiddleware** — origin allow-list driven by the `CORS_ORIGINS` environment variable.

Nginx in the `web` container adds an edge-layer `limit_req_zone` (20 r/s, burst 40) in front of `/api/*`, plus global security headers and a CSP applied to every `location`.

### TLS is a hard prerequisite in production (MEDIUM-12)

The `web` container listens on plain HTTP port 8080 because the official `nginx-unprivileged` image cannot bind 443 without extra capabilities. The container emits `Strict-Transport-Security` and sets JWT cookies without `Secure` unless `COOKIE_SECURE=true` is set — **both only make sense when a TLS-terminating reverse proxy (Caddy, Traefik, an AWS ALB, Cloudflare, ...) sits in front of the container**.

Deployment rules:

- In production, **you must terminate TLS before traffic reaches this container**. Exposing port 80 directly to the internet will ship auth cookies and JWTs in cleartext and silently neuter the HSTS header (browsers will ignore it over HTTP).
- Set `COOKIE_SECURE=true` in the API environment so auth cookies carry the `Secure` attribute. The default is `false` to keep local `docker compose up` usable without a TLS cert.
- Point the TLS proxy at `web:8080` (inside the compose/overlay network) and let it rewrite `X-Forwarded-Proto` to `https`. Uvicorn is launched with `--proxy-headers` (see MEDIUM-2) and will honour the forwarded scheme when generating redirects.

The full deployment checklist lives in `docs/production-hardening-plan.md`.


Additional guardrails:

- Startup validation in `Settings` refuses to boot with a placeholder `JWT_SECRET_KEY` or `ADMIN_PASSWORD`, and rejects a `JWT_SECRET_KEY_PREVIOUS` that is too short or equal to the current key.
- Passwords are hashed with bcrypt (cost factor tuned in `shared/infrastructure/security.py`).
- JWT access tokens are short-lived (default 5 min, capped at 15); refresh tokens can be revoked via the blacklist table.
- `DEBUG=false` (the default) suppresses `/docs`, `/redoc`, and `/openapi.json` so the route list is not exposed to anonymous scanners.
- CORS runs with `allow_credentials=False` because auth is Bearer-token in the `Authorization` header, not cookies.
- The API container's healthcheck only passes once schema init + admin bootstrap + verification succeed, so dependent services never see a half-initialised database.

See `docs/production-hardening-plan.md` for the full checklist and rollout plan.

---

## Documentation

- **`docs/project-spec.md` (v5.1)** — Full system specification. Sections 1–5 are accessible to all team members; sections 6–13 are the technical reference (DB schema, API endpoints, frontend routes, async tasks).
- **`docs/production-hardening-plan.md`** — Security, observability, and operational hardening steps for making the stack production-ready.

---

## Team and Roles

| Member | Role |
|--------|------|
| A (Tech Lead) | Full-stack architecture, core backend, complex frontend, code review |
| B | Frontend: login, dashboard, search, messaging pages |
| C | Frontend: tutor pages, session/exam pages, integration testing |
| D | Database design, presentation slides |
| E | Database design, written documentation |

---

## Known Limitations

- **No real-time messaging.** The chat is polling-based, not WebSocket-based.
- **Not hardened for public deployment.** The Docker stack is intended for classroom demos and development. The production-hardening plan in `docs/` lists what still needs to be done for an internet-facing deployment (TLS termination, secret rotation, backup policy, DB connection-pool sizing under load, etc.).
- **Single-node.** The compose file runs one instance of each service. Horizontal scaling of the API is possible in principle (rate-limit and token-blacklist state is already shared in the DB), but has not been exercised.
