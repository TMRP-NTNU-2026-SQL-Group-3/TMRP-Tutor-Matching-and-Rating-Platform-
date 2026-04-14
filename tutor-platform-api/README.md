# tutor-platform-api

FastAPI + PostgreSQL backend for TMRP (Tutor Matching and Rating Platform). Provides the REST API, authentication, background task worker, and schema bootstrap.

For the project overview, see the [root README](../README.md).

---

## Table of Contents

- [What This Service Does](#what-this-service-does)
- [Requirements](#requirements)
- [Running with Docker](#running-with-docker)
- [Running Locally](#running-locally)
- [Environment Variables](#environment-variables)
- [Code Layout](#code-layout)
- [Request Lifecycle](#request-lifecycle)
- [API Endpoints](#api-endpoints)
- [Database Initialisation](#database-initialisation)
- [Background Worker (Huey)](#background-worker-huey)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

---

## What This Service Does

This process hosts the TMRP HTTP API. It:

- Authenticates users with short-lived JWT access tokens + revocable refresh tokens.
- Enforces domain rules — the match status machine, tutor capacity, the 7-day review lock, session edit auditing, and role-based authorisation.
- Persists all state in PostgreSQL through a connection pool (psycopg2).
- Ships long-running jobs (CSV import/export, seed generation, stats aggregation, scheduled review locking) to a huey worker.
- On first boot, creates the full schema, seeds the subject catalogue, and provisions the super-admin account — idempotently.

The frontend (`tutor-platform-web`) is a pure client of this API.

---

## Requirements

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.10+ | Dataclass + PEP 604 unions used throughout |
| PostgreSQL | 14+ | Dev uses 16; SERIAL / TIMESTAMPTZ / BOOLEAN required |
| pip / virtualenv | — | Any |
| (optional) Docker | 20+ | For containerised runs |

Windows users can run either natively (the project ships a `start.bat`) or via Docker.

---

## Running with Docker

The root `docker-compose.yml` builds this service alongside the database, worker, and web. From the **repository root**:

```bash
cp tutor-platform-api/.env.docker.example tutor-platform-api/.env.docker
# Edit .env.docker: set a real JWT_SECRET_KEY and ADMIN_PASSWORD
docker compose up -d --build
```

Once healthy, the API is at <http://localhost:8000> and Swagger UI at <http://localhost:8000/docs>.

The container's healthcheck (`GET /health`) only passes after:
1. the connection pool is initialised,
2. the schema DDL has run,
3. the subject seeds are in place,
4. the admin account exists.

`docker-compose.yml` sets `start_period: 30s` so dependent services (web) wait until the API is actually ready.

---

## Running Locally

For active development without Docker:

```bash
# 1. Start a local PostgreSQL and create the database
createdb tmrp

# 2. Install dependencies
cd tutor-platform-api
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env:
#   - Set DATABASE_URL to your local DB
#   - Generate JWT_SECRET_KEY:
#       python -c "import secrets; print(secrets.token_hex(32))"
#   - Set ADMIN_PASSWORD to something that's not the default

# 4. Start everything (Windows)
start.bat
```

`start.bat` launches three terminals:
- **huey worker** — `huey_consumer app.worker.huey`
- **FastAPI** — `uvicorn app.main:app --reload --port 8000`
- **Vite dev server** — the web frontend

On non-Windows platforms, run each command manually in its own shell.

---

## Environment Variables

Loaded by pydantic-settings from `.env` (local) or `.env.docker` (container).

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql://tmrp:tmrp@localhost:5432/tmrp` | PostgreSQL connection string |
| `DB_POOL_MIN` | `2` | Minimum size of the psycopg2 connection pool |
| `DB_POOL_MAX` | `10` | Maximum pool size |
| `JWT_SECRET_KEY` | **required** | HMAC secret for signing JWTs. `change-me-in-production` is rejected at startup. |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_EXPIRE_MINUTES` | `5` | Access token TTL in minutes (paired with refresh-token flow; capped at 15) |
| `ADMIN_USERNAME` | `admin` | Super-admin login |
| `ADMIN_PASSWORD` | **required** | Super-admin password. `admin123` is rejected at startup. |
| `REVIEW_LOCK_DAYS` | `7` | Days after which a review locks |
| `HUEY_DB_PATH` | `data/huey.db` | SQLite file backing the huey queue |
| `LOG_FILE` | `logs/app.log` | Rotating log file path |
| `LOG_LEVEL` | `INFO` | Log level |
| `LOG_FORMAT` | `json` | `json` or `text` |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated list of allowed origins |

> **Security:** `Settings.validate_security_defaults` fails fast if either `JWT_SECRET_KEY` or `ADMIN_PASSWORD` is still at its placeholder value. This is intentional — the server refuses to boot rather than silently running with insecure defaults.

---

## Code Layout

```
tutor-platform-api/
├── Dockerfile
├── requirements.txt
├── start.bat                   # Local one-click launcher
├── .env.example                # Local template
├── .env.docker.example         # Container template
│
├── app/
│   ├── main.py                 # FastAPI app: lifespan, middleware, routers
│   ├── init_db.py              # Schema DDL + subject seeds + admin bootstrap
│   ├── worker.py               # huey instance
│   ├── config.py               # (legacy) — active settings live in shared/infrastructure/config.py
│   ├── database.py             # (legacy) connection helpers
│   ├── database_tx.py          # Transaction helpers
│   ├── dependencies.py         # FastAPI Depends(): current_user, role checks, DB cursor
│   ├── exceptions.py           # (legacy) — DomainException now in shared/domain
│   │
│   ├── shared/                 # Shared kernel
│   │   ├── domain/             # IDs, errors, protocols
│   │   ├── infrastructure/     # config, database pool, logger, security (hashing, JWT)
│   │   └── api/                # health_router, common response shape
│   │
│   ├── identity/               # Bounded Context: auth / users
│   │   ├── api/                # auth_router: /api/auth/*
│   │   ├── domain/             # User entity, role value objects
│   │   └── infrastructure/     # PostgresUserRepository
│   │
│   ├── catalog/                # BC: tutors, students, subjects
│   ├── matching/               # BC: matches, status machine, contracts
│   │   ├── api/
│   │   ├── application/        # CreateMatchUseCase etc.
│   │   ├── domain/             # Match aggregate, status transitions
│   │   └── infrastructure/
│   ├── teaching/               # BC: sessions, exams, edit logs
│   ├── review/                 # BC: three-way ratings, 7-day lock
│   ├── messaging/              # BC: conversations, messages
│   ├── analytics/              # BC: income / expense aggregations
│   ├── admin/                  # BC: CSV ops, seed, task status
│   │
│   ├── middleware/
│   │   ├── request_id.py       # X-Request-ID in/out
│   │   ├── security_headers.py # CSP, HSTS, X-Frame-Options, ...
│   │   ├── access_log.py       # Structured request/response logs
│   │   └── rate_limit.py       # DB-backed token bucket
│   │
│   ├── routers/                # (legacy flat routers — being migrated into BCs)
│   ├── repositories/           # (legacy repos)
│   ├── models/                 # (legacy DTOs)
│   ├── tasks/                  # huey tasks (import_export, scheduled, seed, stats)
│   └── utils/                  # csv_handler, columns, logger, security helpers
│
├── seed/
│   ├── generator.py            # Fake data builder (users, tutors, matches, sessions, ...)
│   └── output/                 # Generated CSV fixtures
│
├── data/
│   ├── huey.db                 # SQLite task queue (created at runtime)
│   └── ...                     # Persistent volume in Docker
│
├── logs/                       # Rotating log files
└── tests/
```

> **Note on the legacy/DDD split.** The project is mid-migration: new features go into the `app/<context>/` Bounded Contexts, while the flat `routers/`, `repositories/`, and `models/` layout is the fallback for code that hasn't been refactored yet. The target structure is defined in `../docs/ddd-migration-spec.md`. External API paths are stable throughout the migration.

---

## Request Lifecycle

Middleware is registered in `app/main.py` in this order. Starlette wraps middleware inside-out, so the outermost (first to see a request) is the **last** one registered:

```
Browser
  │
  ▼ CORSMiddleware                 (outermost — handles preflight, attaches CORS headers)
  ▼ RequestIDMiddleware            (assigns X-Request-ID)
  ▼ SecurityHeadersMiddleware      (adds CSP, HSTS, ...)
  ▼ AccessLogMiddleware            (structured log with request_id + timing)
  ▼ RateLimitMiddleware            (innermost — uses rate_limit_hits table)
  ▼ Router
     └─ Dependency injection: current_user, role guard, DB cursor
        └─ Application service / Use case
           └─ Domain layer
              └─ Repository (Infrastructure)
                 └─ PostgreSQL
```

Exception handlers (also in `main.py`):

| Exception | Status | Response shape |
|-----------|--------|----------------|
| `DomainException` | mapped from `exc.status_code` | `{success: false, data: null, message}` |
| `RequestValidationError` | 422 | `{success: false, data: null, message, errors: [...]}` |
| `StarletteHTTPException` | passthrough | `{success: false, data: null, message}` |
| Any other `Exception` | 500 | `{success: false, data: null, message, request_id}` + `X-Request-ID` header |

---

## API Endpoints

All paths are prefixed with `/api` except `/health`. Full Pydantic schemas are visible in Swagger at `/docs`.

| Prefix | Module | Bounded Context |
|--------|--------|-----------------|
| `/health` | `shared.api.health_router` | shared |
| `/api/auth` | `identity.api.router` | identity |
| `/api/tutors` | `catalog.api.tutor_router` | catalog |
| `/api/students` | `catalog.api.student_router` | catalog |
| `/api/subjects` | `catalog.api.subject_router` | catalog |
| `/api/matches` | `matching.api.router` | matching |
| `/api/sessions` | `teaching.api.session_router` | teaching |
| `/api/exams` | `teaching.api.exam_router` | teaching |
| `/api/reviews` | `review.api.router` | review |
| `/api/messages` | `messaging.api.router` | messaging |
| `/api/stats` | `analytics.api.router` | analytics |
| `/api/admin` | `admin.api.router` | admin |

### Auth

```http
POST /api/auth/register
POST /api/auth/login        → { access_token, refresh_token }
POST /api/auth/refresh      → new access token (refresh-token blacklist checked)
POST /api/auth/logout       → revokes refresh token (adds jti to blacklist)
GET  /api/auth/me
```

Protected endpoints require:

```http
Authorization: Bearer <access_token>
```

Role enforcement is declarative:

```python
@router.post("/", dependencies=[Depends(require_role("parent"))])
```

Returns 403 if the current user's role doesn't match.

### Response envelope

Success:
```json
{ "success": true, "data": { "...": "..." }, "message": null }
```

Failure:
```json
{ "success": false, "data": null, "message": "人類可讀的錯誤訊息" }
```

500 responses additionally include a `request_id` that matches the `X-Request-ID` response header — useful when users report bugs.

---

## Database Initialisation

`app/init_db.py` owns the schema. It is **idempotent** — safe to run on every boot.

Bootstrap flow (called from `app.main.lifespan`):

1. `init_pool()` — open the psycopg2 connection pool using `DATABASE_URL`.
2. `create_schema(conn)` — run the `SCHEMA_DDL` string. Every `CREATE TABLE` and `CREATE INDEX` uses `IF NOT EXISTS`.
3. `seed_subjects(conn)` — insert the 12 subject rows if `subjects` is empty.
4. `ensure_admin_user(conn, settings)` — insert the super-admin if no account with `ADMIN_USERNAME` exists.

If any step fails, the lifespan hook re-raises and the server refuses to serve requests — a half-initialised state would be worse than a crash loop.

### Tables created

Business (13): `users`, `tutors`, `students`, `subjects`, `tutor_subjects`, `tutor_availability`, `conversations`, `messages`, `matches`, `sessions`, `session_edit_logs`, `exams`, `reviews`.

Support (2): `refresh_token_blacklist`, `rate_limit_hits`. These back auth and rate-limit state so state is consistent across multiple API workers.

Unique indexes enforce: one username per user, one subject per name, one tutor row per user, one conversation per user pair, and one review per `(match_id, reviewer_user_id, review_type)`.

---

## Background Worker (Huey)

The worker is a separate process (`huey_consumer app.worker.huey`). In Docker it runs in its own container; locally it's launched by `start.bat`.

Queue storage: SQLite file at `data/huey.db` (shared volume with the API in Docker).

Tasks live in `app/tasks/`:

| Task | Module | Trigger |
|------|--------|---------|
| `import_csv_task` | `import_export.py` | Admin action |
| `export_csv_task` | `import_export.py` | Admin action |
| `generate_seed_data` | `seed_tasks.py` | Admin action |
| `calculate_income_stats` | `stats_tasks.py` | Admin / scheduled |
| `calculate_expense_stats` | `stats_tasks.py` | Admin / scheduled |
| `lock_expired_reviews` | `scheduled.py` | Cron (03:00 daily) |

Admin-triggered tasks return a `task_id` immediately. The frontend polls `GET /api/admin/tasks/{task_id}` for status (`pending`, `running`, `success`, `failure`) and the final result or error.

Scheduled tasks use huey's `@crontab()` decorator; the worker must be running for them to fire.

---

## Testing

```bash
cd tutor-platform-api
pytest
```

The `tests/` folder contains integration tests that hit a real PostgreSQL database. Configure the test database via the same `DATABASE_URL` variable (use a separate database — tests are destructive).

Per the DDD migration plan, new domain logic should get pure unit tests that don't need FastAPI or the database. See `../docs/ddd-migration-spec.md` §10 for the target testing strategy.

---

## Troubleshooting

**"JWT_SECRET_KEY 必須在 .env 中設定安全的密鑰"** at startup
The server refuses to run with the default secret. Generate one:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**"ADMIN_PASSWORD 必須在 .env 中設定強密碼"** at startup
Same idea — replace the placeholder in `.env`.

**`psycopg2.OperationalError: could not connect to server`**
The API booted before PostgreSQL was accepting connections. In Docker, `depends_on: db.condition: service_healthy` should prevent this; if you see it in compose, check `docker compose logs db`. Locally, make sure PostgreSQL is running and `DATABASE_URL` is correct.

**Schema init fails repeatedly**
`init_db.py` is idempotent — if it keeps failing, the DDL itself is the problem (e.g. a manually edited DB with a conflicting older schema). Drop the database and let the API recreate it:
```bash
docker compose down -v   # wipes the pgdata volume
docker compose up -d --build
```

**Background tasks never run**
The huey worker is a separate process. If you start only the API, admin actions will return a `task_id` but no task will ever complete. Start the worker (`huey_consumer app.worker.huey`) or use `docker compose up` which starts everything.

**500 errors I can't reproduce**
Every 500 response includes an `X-Request-ID` header (and a `request_id` field in the body). Grep the logs for that ID to find the full stack trace with surrounding request context.
