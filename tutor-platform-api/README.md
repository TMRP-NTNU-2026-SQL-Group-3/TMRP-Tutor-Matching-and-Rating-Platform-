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

With the auto-loaded `docker-compose.override.yml`, the API is reachable at <http://127.0.0.1:8001> on the host (the override binds `127.0.0.1:8001 → container:8000`). The production compose (`docker compose -f docker-compose.yml up`) does **not** publish the API port — all traffic must go through Nginx in the `web` container at `/api/*`. Swagger UI at `/docs` is only served when both `DEBUG=true` and `ENABLE_DOCS=true` (the startup validator rejects `ENABLE_DOCS=true` when `DEBUG=false`).

The container's healthcheck (`GET /health`) only passes after:
1. the connection pool is initialised,
2. the schema DDL has run,
3. the subject seeds are in place,
4. the admin account exists.

`docker-compose.yml` sets `start_period: 90s` so dependent services (web) wait until the API is actually ready (covers the first cold-start DDL + seed run).

> `DATABASE_URL` for the container is composed by `docker-compose.yml` from the repo-root `.env` (`DB_USER`, `DB_PASSWORD`, `DB_NAME`) so the same credentials serve both Postgres and the API. Do **not** set `DATABASE_URL` in `.env.docker` — compose will override it, and a stale value there is confusing.

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
| `DATABASE_URL` | **required** | PostgreSQL connection string (no default — must be set). In compose, built from the repo-root `.env`. |
| `DB_POOL_MIN` | `5` | Minimum size of the psycopg2 connection pool |
| `DB_POOL_MAX` | `20` | Maximum pool size |
| `DB_PER_USER_QUOTA` | `5` | Maximum number of simultaneous in-flight requests a single authenticated user may hold open. Enforced per worker process in memory. Excess requests receive 429 with `Retry-After: 1`. |
| `JWT_SECRET_KEY` | **required**, >= 32 chars | HMAC secret for signing JWTs. Placeholder values (`change-me`, `change-me-in-production`) are rejected at startup. |
| `JWT_SECRET_KEY_PREVIOUS` | `""` | Optional prior key for rotation windows. If set, verification accepts tokens signed by either key. Must be >= 32 chars and differ from the current key. Requires `JWT_SECRET_KEY_PREVIOUS_EXPIRES_AT` to be set. |
| `JWT_SECRET_KEY_PREVIOUS_EXPIRES_AT` | `""` | ISO 8601 UTC deadline after which the previous key stops being accepted (e.g. `"2026-05-01T00:00:00Z"`). Required when `JWT_SECRET_KEY_PREVIOUS` is set; must not exceed 7 days from now. |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_EXPIRE_MINUTES` | `5` | Access token TTL in minutes. Hard-capped at 10 by a lifespan check because access tokens are not revoked on logout. |
| `ADMIN_USERNAME` | `admin` | Super-admin login. Must not be `admin` or the onboarding placeholder when `DEBUG=false`. |
| `ADMIN_PASSWORD` | **required**, >= 16 chars | Super-admin password. Must contain all four character classes (lowercase, uppercase, digit, symbol). Known placeholders (`admin`, `admin123`, `password`) are rejected at startup. |
| `REVIEW_LOCK_DAYS` | `7` | Days after which a review locks |
| `ADMIN_MAX_UPLOAD_BYTES` | `52428800` | Upper bound on admin CSV/ZIP import size (50 MB) |
| `ADMIN_MAX_IMPORT_ROWS_PER_TABLE` | `50000` | Row cap per table for admin imports |
| `MAX_REQUEST_BODY_BYTES` | `52428800` | Global HTTP body cap enforced by `BodySizeLimitMiddleware` (50 MB, matches the admin upload cap) |
| `HUEY_DB_PATH` | `data/huey.db` | SQLite file backing the huey queue |
| `LOG_FILE` | `logs/app.log` | Rotating log file path |
| `LOG_LEVEL` | `INFO` | Log level |
| `LOG_FORMAT` | `json` | `json` or `text` |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated list of allowed origins. For local Vite dev override to `http://localhost:5273` (Vite port is 5273 in this project). Must use `https://` in non-debug mode. |
| `COOKIE_SECURE` | `false` | Sets the `Secure` attribute on auth cookies. Must be `true` when `DEBUG=false` (enforced at startup). Leave `false` for local HTTP development only. |
| `DEBUG` | `false` | When `false`, enforces `COOKIE_SECURE=true`, `https://` CORS origins, and rejects `ENABLE_DOCS=true`. |
| `ENABLE_DOCS` | `false` | When `true`, exposes `/docs`, `/redoc`, and `/openapi.json`. The startup validator rejects `ENABLE_DOCS=true` when `DEBUG=false`, so schema endpoints can only be enabled in debug (development/staging) deployments. |

> **Security:** the `Settings` model validator fails fast on placeholder secrets, short keys, and a `JWT_SECRET_KEY_PREVIOUS` that equals the current key. The server refuses to boot rather than silently running with insecure defaults.

---

## Code Layout

```
tutor-platform-api/
├── Dockerfile
├── requirements.txt
├── start.bat                   # Local one-click launcher (Windows)
├── .env.example                # Local template
├── .env.docker.example         # Container template
│
├── app/
│   ├── main.py                 # FastAPI app: lifespan, middleware, routers, exception handlers
│   ├── init_db.py              # Schema DDL + subject seeds + admin bootstrap + verification
│   ├── worker.py               # huey instance
│   │
│   ├── shared/                 # Shared kernel (cross-context)
│   │   ├── api/                # health_router, common response envelope, schemas, validators
│   │   ├── domain/             # DomainException, ID types, repository ports
│   │   └── infrastructure/     # config (Settings), database pool, database_tx,
│   │                           # base_repository, postgres_unit_of_work, logger,
│   │                           # security (bcrypt + JWT), huey_json_serializer,
│   │                           # column_validation
│   │
│   ├── identity/               # Bounded Context: auth / users
│   │   ├── api/                # /api/auth/* router + schemas + dependencies
│   │   ├── domain/             # User entity, role value objects
│   │   └── infrastructure/     # PostgresUserRepository
│   │
│   ├── catalog/                # BC: tutors, students, subjects (api/, domain/, infrastructure/)
│   ├── matching/               # BC: matches, status machine, contracts
│   │   ├── api/
│   │   ├── application/        # Use cases (CreateMatch, transition handlers, ...)
│   │   ├── domain/             # Match aggregate, status transitions
│   │   └── infrastructure/
│   ├── teaching/               # BC: sessions, exams, edit logs (api/, application/, domain/, infrastructure/)
│   ├── review/                 # BC: three-way ratings, 7-day lock (api/, domain/, infrastructure/)
│   ├── messaging/              # BC: conversations, messages (api/, application/, domain/, infrastructure/)
│   ├── analytics/              # BC: income / expense aggregations (api/, application/, infrastructure/)
│   ├── admin/                  # BC: CSV ops, seed, task status (api/, application/, domain/, infrastructure/)
│   │
│   ├── middleware/
│   │   ├── request_id.py       # X-Request-ID in/out
│   │   ├── body_size_limit.py  # Reject oversized request bodies before handlers read them
│   │   ├── security_headers.py # CSP, HSTS, X-Frame-Options, ...
│   │   ├── access_log.py       # Structured request/response logs
│   │   ├── rate_limit.py       # DB-backed sliding window (rate_limit_hits; per-path limits, fail-closed on sensitive endpoints)
│   │   ├── user_quota.py       # Per-user in-flight request cap (DB_PER_USER_QUOTA, default 5)
│   │   └── csrf.py             # Double-submit cookie: validates X-CSRF-Token header == csrf_token cookie
│   │
│   ├── tasks/                  # huey tasks: import_export, scheduled, seed_tasks, stats_tasks
│   └── utils/                  # csv_handler, logger, security helpers
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
└── tests/                      # pytest integration tests: test_auth, test_matches,
                                # test_match_state_machine, test_sessions, test_reviews,
                                # test_admin_operations, test_middleware, test_password_policy,
                                # test_refresh_and_logout, test_sql_injection (+ conftest.py)
```

> **DDD layout.** All HTTP routing, data access, and domain rules now live under `app/<context>/` Bounded Contexts plus the `app/shared/` kernel. Legacy flat layouts (`app/routers/`, `app/repositories/`, `app/models/`, top-level `config.py` / `database.py` / `exceptions.py`) have been removed. External API paths are unchanged.

---

## Request Lifecycle

Middleware is registered in `app/main.py` in this order. Starlette wraps middleware inside-out, so the outermost (first to see a request) is the **last** one registered:

```
Browser
  │
  ▼ CORSMiddleware                 (outermost — handles preflight, attaches CORS headers;
  │                                 allow_credentials=True — auth uses HttpOnly cookies; Bearer header
  │                                 accepted as fallback for Swagger UI)
  ▼ RequestIDMiddleware            (assigns X-Request-ID; value threaded into logs + 500 bodies)
  ▼ BodySizeLimitMiddleware        (rejects payloads over MAX_REQUEST_BODY_BYTES;
  │                                 inside RequestID so the rejection log carries request_id)
  ▼ SecurityHeadersMiddleware      (adds CSP, HSTS, X-Frame-Options, ...)
  ▼ AccessLogMiddleware            (structured log with request_id + timing)
  ▼ UserConcurrencyQuotaMiddleware (per-user in-flight cap; 429 + Retry-After: 1 when exceeded)
  ▼ CSRFMiddleware                 (double-submit: validates X-CSRF-Token header == csrf_token cookie
  │                                 on all mutating requests; rejected before the rate-limit bucket
  │                                 is debited, preserving the victim's remaining tokens)
  ▼ RateLimitMiddleware            (innermost — uses rate_limit_hits table, shared across workers)
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

All paths are prefixed with `/api` except `/health`. Full Pydantic schemas are visible in Swagger at `/docs` when `DEBUG=true` — in the default hardened mode (`DEBUG=false`), `/docs`, `/redoc`, and `/openapi.json` all return 404 to avoid leaking the route inventory.

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
POST /api/auth/login        → sets HttpOnly cookies (access_token, refresh_token, csrf_token); body carries user info only
POST /api/auth/refresh      → rotates all three cookies; refresh token read from cookie only
POST /api/auth/logout       → revokes refresh token (adds jti to blacklist), clears cookies
GET  /api/auth/me
PUT  /api/auth/me           → update display_name, phone, email
PUT  /api/auth/password     → change password (validates current; rejects last 5 hashes)
```

Auth tokens are delivered as HttpOnly cookies (`access_token` scoped to `/api`, `refresh_token` scoped to `/api/auth`). Login also sets a readable `csrf_token` cookie (scoped to `/`); every mutating request must echo it in the `X-CSRF-Token` header — `CSRFMiddleware` rejects requests where the values do not match. Protected endpoints read from the cookie first; a `Bearer` header is accepted as fallback for Swagger UI. Pass tokens via cookie in production — using the Bearer fallback from a browser page bypasses CSRF mitigations.

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
3. `seed_subjects(conn)` — insert the subject rows if `subjects` is empty.
4. `ensure_admin_user(conn, settings)` — insert the super-admin if no account with `ADMIN_USERNAME` exists.
5. `verify_bootstrap(conn, settings)` — sanity-check that the schema, seeds, and admin account all made it in.

If any step fails, the lifespan hook re-raises and the server refuses to serve requests — a half-initialised state would be worse than a crash loop.

### Tables created

Business (14): `users`, `tutors`, `students`, `subjects`, `tutor_subjects`, `tutor_availability`, `conversations`, `messages`, `matches`, `sessions`, `session_edit_logs`, `exams`, `reviews`, `password_history`.

Support (3): `refresh_token_blacklist`, `rate_limit_hits`, `audit_log`. The first two back auth and rate-limit state so it is consistent across multiple API workers. `audit_log` records privileged-action history (actor, action, resource type/ID, old/new values); `actor_user_id` uses `ON DELETE SET NULL` and `resource_id` carries no FK so the trail survives both account removal and row deletion.

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

Existing coverage spans authentication (`test_auth.py`, `test_refresh_and_logout.py`, `test_password_policy.py`), matching (`test_matches.py`, `test_match_state_machine.py`), teaching (`test_sessions.py`), reviews (`test_reviews.py`), admin operations (`test_admin_operations.py`), middleware behaviour (`test_middleware.py`), and SQL-injection regression suites (`test_sql_injection.py`). New domain logic added under `app/<context>/domain/` should get pure unit tests that don't need FastAPI or the database; keep integration tests for API-level behaviour and DB constraints.

---

## Troubleshooting

**`ValueError: JWT_SECRET_KEY must be a real secret.`** at startup
The server refuses to run with a placeholder key. Generate one:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**`ValueError: ADMIN_PASSWORD must contain all four character classes`** at startup
Replace the placeholder in `.env`. The password must be at least 16 characters and include lowercase, uppercase, a digit, and a symbol.

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
