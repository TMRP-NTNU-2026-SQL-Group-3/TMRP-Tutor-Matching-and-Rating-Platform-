# TMRP Project Audit Report

**Date:** 2026-05-13  
**Branch:** `main`  
**Scope:** Full codebase — API routes, database, authentication, tests, infrastructure, spec compliance  
**Method:** Four parallel static-analysis agents examining disjoint areas of the codebase

---

## Executive Summary

| Severity | Count |
|----------|-------|
| Critical | 2 |
| High | 14 |
| Medium | 34 |
| Low | 54 |
| **Total** | **104** |

The two most consequential systemic problems are:

1. **Background tasks are dead code.** The Huey task infrastructure (`stats_tasks.py`, `import_csv_task`, `export_csv_task`) is defined but never dispatched from the API layer. Stats, import, and export all run synchronously in request handlers. The spec, README, and background-task table in the README all describe an async-worker architecture that does not exist at runtime.

2. **The test suite has structural failures.** Two core success-path tests (`test_register_*`, `test_login_success`) will fail when run: register tests assert HTTP 200 but the route returns 201, and the login test asserts `"access_token" in data` but tokens are now delivered via HttpOnly cookies. Six entire endpoint groups (students, tutors, subjects, messaging, analytics, exams) have zero test coverage.

---

## Section 1 — Business Logic & API Routes

### Critical

**F-01 — Reviews permitted on active and paused matches**
- File: `tutor-platform-api/app/review/application/review_service.py:27`
- `_REVIEWABLE_STATUSES = frozenset({"active", "paused", "ended"})` — the spec requires that reviews may only be submitted after a match reaches `ended` status. Allowing reviews on live matches violates the core business rule.

**F-02 — Idempotency key double-commit / transaction ordering hazard**
- File: `tutor-platform-api/app/matching/api/router.py:36–67`
- `conn.commit()` is called manually at line 67 on the idempotency INSERT, while `service.create_match` wraps its own Unit-of-Work that also commits. If the service's UoW already committed, a failure in the subsequent idempotency INSERT leaves the connection in an inconsistent state with no rollback path.

---

### High

**F-03 — Session routes use flat paths instead of spec-required nested paths**
- File: `tutor-platform-api/app/teaching/api/session_router.py:21,47`
- Spec §7.6 defines `GET /api/matches/{match_id}/sessions` and `POST /api/matches/{match_id}/sessions`. Implementation uses `GET /api/sessions?match_id=` and `POST /api/sessions` with `match_id` in body. Frontend code following the spec will receive 404s.

**F-04 — Exam routes use flat paths instead of spec-required nested paths**
- File: `tutor-platform-api/app/teaching/api/exam_router.py:21,35`
- Spec §7.7 defines `GET /api/students/{student_id}/exams` and `POST /api/students/{student_id}/exams`. Implementation uses flat query-param routes.

**F-05 — Review create/list routes use flat paths instead of spec-required nested paths**
- File: `tutor-platform-api/app/review/api/router.py:25,35`
- Spec §7.8 defines `POST /api/matches/{match_id}/reviews` and `GET /api/matches/{match_id}/reviews`. Implementation uses `POST /api/reviews` (match_id in body) and `GET /api/reviews?match_id=`.

**F-06 — Admin reset is two-step; spec and frontend expect single-step `POST /api/admin/reset`**
- File: `tutor-platform-api/app/admin/api/router.py:165,181`
- The implementation correctly uses a two-step flow (`/reset/request` + `/reset/confirm`) for security, but neither path matches the spec-documented route. Any frontend following the spec will break.

**F-07 — Admin import uses query param; spec defines path parameter**
- File: `tutor-platform-api/app/admin/api/router.py:102`
- Spec §7.10 defines `POST /api/admin/import/{table_name}`. Implementation registers `POST /api/admin/import` with `table_name` as a query parameter.

**F-08 — `GET /api/students` restricted to parents only; tutors are excluded**
- File: `tutor-platform-api/app/catalog/api/student_router.py:17`
- `require_role("parent")` locks the endpoint. Spec §7.3 states tutors should be able to list their matched students through this endpoint.

**F-09 — Tutor search has no role restriction; spec prohibits tutors from searching tutors**
- File: `tutor-platform-api/app/catalog/api/tutor_router.py:47`
- `get_current_user` is used (any authenticated user), but spec permissions table §4.2 explicitly marks tutor-searching-tutor as prohibited.

**F-10 — TOCTOU race in `update_status`: unlocked read before transaction**
- File: `tutor-platform-api/app/matching/application/match_app_service.py:131–138`
- `find_by_id` (unlocked) sets `old_status` and `is_parent`/`is_tutor` flags used for permission checking at line 137. The row is re-read under lock inside each branch, but the unlocked read's `old_status` value determines which branch is taken.

**SEC-4 — Register tests assert HTTP 200 but route returns 201 — tests always fail**
- File: `tutor-platform-api/tests/test_auth.py:35,54`
- Both `test_register_parent_success` and `test_register_tutor_success` will fail on every run, leaving the registration success path effectively uncovered by any passing test.

**SEC-5 — Login success test asserts `"access_token" in data` but tokens are now in cookies**
- File: `tutor-platform-api/tests/test_auth.py:116–117`
- Since the SEC-C02 change, `AuthUserResponse` only serializes `user_id`, `role`, `display_name`. The assertion will always be `False`, making the login success path untested.

**SEC-7 — Zero test coverage for 6 entire endpoint groups**
- No test file covers: students, tutors, subjects, messaging, analytics, or exams routers. Regressions in any of these areas will not be caught.

**SEC-8 — Admin reset flow has zero tests**
- The most destructive admin operation — database reset with token sub binding, JTI single-use enforcement, advisory lock, and per-user rate limiting — has no test coverage.

**SEC-9 — Admin import/export endpoints have zero tests**
- `POST /api/admin/import`, `GET /api/admin/export/{table_name}`, `POST /api/admin/import-all`, `GET /api/admin/export-all` — including the `EXPORT_DENYLIST` (`users` table) and `clear_first=True` path — are untested.

---

### Medium

**F-11 — `GET /api/subjects` has no authentication guard (undocumented design decision)**
- File: `tutor-platform-api/app/catalog/api/subject_router.py:11`
- This is consistent with treating subjects as public reference data, but spec §4.2 does not explicitly mark it as public. The intent is not documented.

**F-12 — `ReviewUpdate` schema cannot prevent nullifying mandatory rating axes**
- File: `tutor-platform-api/app/review/api/schemas.py:52–78`
- A parent who originally submitted a compliant 4-axis `parent_to_tutor` review can PATCH `rating_3: null`, stripping a mandatory axis. The schema validation does not guard against this.

**F-13 — `DELETE /api/sessions/{id}` exists in implementation but not in spec**
- File: `tutor-platform-api/app/teaching/api/session_router.py:82`
- Spec §7.6 does not define a DELETE endpoint for sessions. The endpoint is undocumented and untested.

**F-14 — `GET /api/matches` has no `status` filter despite spec documenting one**
- File: `tutor-platform-api/app/matching/api/router.py:72`
- Spec §7.5 describes `GET /api/matches` as supporting a `status` query filter. Neither the router nor the service layer accepts this parameter.

**F-15 — `update_review` does not prevent nullifying a mandatory `parent_to_tutor` rating axis**
- File: `tutor-platform-api/app/review/application/review_service.py:78–127`
- If the caller explicitly passes `rating_3: null` on a PATCH, the service will call `repo.update(review_id, {"rating_3": null})` without checking mandatory-axis completeness.

**F-16 — `POST /api/admin/import-all` reads ZIP bytes without an enforced size limit**
- File: `tutor-platform-api/app/admin/api/router.py:425`
- The single-CSV import checks `MAX_UPLOAD_SIZE + 1` before processing. The ZIP upload calls `file.file.read()` without a size cap, risking memory exhaustion on large uploads.

**F-17 — Domain invariant weaker than API schema: `Contract` allows `hourly_rate=0`, API requires `>= 1`**
- Files: `tutor-platform-api/app/matching/api/schemas.py:15`, `tutor-platform-api/app/matching/domain/value_objects.py:85`
- A zero-rate contract can be constructed internally (e.g., via CSV import) even though the API rejects it.

**F-18 — Stats endpoints compute synchronously; spec requires background task dispatch**
- Files: `tutor-platform-api/app/analytics/api/router.py:41,54`, `tutor-platform-api/app/tasks/stats_tasks.py`
- `calculate_income_stats` and `calculate_expense_stats` Huey tasks exist but are never dispatched. The analytics routes call the service directly and block the request worker thread.

**SEC-1 — `X-Request-ID` header echoed from client without sanitization (log injection)**
- File: `tutor-platform-api/app/middleware/request_id.py:10`
- Client-supplied values are written directly into logs and response headers with no length cap, whitelist pattern, or CRLF stripping.

**SEC-2 — Access tokens not blacklisted after admin-forced password reset**
- File: `tutor-platform-api/app/main.py:177–189`
- After `POST /api/admin/users/{user_id}/reset-password`, the target user's existing access tokens remain valid for up to 5 minutes. Only refresh tokens are blacklisted.

**SEC-6 — Login success test does not verify cookie delivery (HttpOnly, SameSite, Secure flags)**
- File: `tutor-platform-api/tests/test_auth.py:113–117`
- The entire SEC-C02 cookie-based auth mechanism is unverified in the test suite.

**SEC-10 — `PUT /api/auth/me` has zero tests, including no CSRF double-submit verification**
- File: `tutor-platform-api/tests/test_auth.py`
- No test verifies that the `X-CSRF-Token` header is required for the update-me endpoint.

**SEC-11 — SQL injection tests do not cover free-text fields (comment, content_summary, message content)**
- File: `tutor-platform-api/tests/test_sql_injection.py`
- Only `username`, `display_name`, and `invite_message` are exercised by the injection regression suite.

**SEC-12 — No test asserts `_CSRF_EXEMPT_PATHS` membership as a security invariant**
- File: `tutor-platform-api/tests/test_middleware.py`
- Accidentally adding a new path to the CSRF exempt set would not be caught by the existing tests.

**SEC-13 — Admin read endpoints (system-status, tables, users list) have zero tests**
- No test verifies that non-admins receive 403 on any admin read endpoint.

**SEC-14 — `GET /api/admin/tasks/{task_id}` no-pickle invariant is untested**
- File: `tutor-platform-api/app/admin/api/router.py:439–490`
- The security-critical pickle-refusal logic has no test coverage.

**SEC-15 — `GET /api/tutors` requires auth; inconsistent with public `GET /api/subjects`**
- File: `tutor-platform-api/app/catalog/api/tutor_router.py:47`
- The browsing restriction may be intentional, but it is untested and undocumented.

**SEC-17 — `.env.example` documents wrong admin password requirements**
- File: `tutor-platform-api/.env.example:24`
- Documents "min 12 chars, 3 of 4 classes" but `config.py` enforces 16 chars with all 4 classes required. Operators following the example would get a confusing startup failure.

**SEC-18 — `.env.docker.example` CORS origins (HTTP) combined with `COOKIE_SECURE=true` is unusable**
- File: `tutor-platform-api/.env.docker.example:32–35`
- Setting `CORS_ORIGINS=http://localhost` + `COOKIE_SECURE=true` with `DEBUG=false` causes a config validation failure at startup. The template cannot be used as-is.

**SEC-21 — `POST /api/admin/import-all` (ZIP) skips Content-Type validation**
- File: `tutor-platform-api/app/admin/api/router.py:414`
- Single-CSV import validates Content-Type; the ZIP upload does not, creating an inconsistent defense-in-depth posture.


2026-05-13 fixed (above)


~~**A-1 — `pg_isready -U ${DB_USER}` may not expand in CMD-SHELL**~~
- ~~File: `docker-compose.yml:49`~~
- ~~`DB_USER` may not be exported as a shell variable inside the healthcheck exec context, causing `pg_isready` to use the default user and potentially return false-positive healthy results.~~
- **Fixed 2026-05-14**: Changed to `pg_isready -U $$POSTGRES_USER`. `$$` escapes Docker Compose interpolation; the shell inside the container resolves `$POSTGRES_USER` from the container's own environment (where the `db` service explicitly sets it). This guarantees the correct user is probed regardless of the host environment.

~~**A-2 — `web` (Nginx) service has no healthcheck**~~
- ~~File: `docker-compose.yml:160–191`~~
- ~~`db`, `api`, and `worker` all have healthchecks; the `web` service does not. Silent Nginx failures will not be detected by Docker's health monitoring.~~
- **Fixed 2026-05-14**: Added `wget -qO /dev/null http://localhost:8080/ || exit 1` healthcheck to the `web` service (interval 10s, timeout 5s, 3 retries, 10s start period). `wget` is available in nginx:alpine without additional installation.


~~**C-1 — `docker-compose.run.yml` has `DEBUG=true` + `COOKIE_SECURE=false` with no production guard**~~
- ~~File: `docker-compose.run.yml:9–20`~~
- ~~A developer who includes this file in a public-facing stack will expose `/docs`, `/redoc`, `/openapi.json` and strip the `Secure` flag from JWT cookies. There is no entrypoint-level guard against this misconfiguration.~~
- **Fixed 2026-05-14**: `docker-entrypoint.sh` now refuses to start when `DEBUG=true` unless `ALLOW_DEBUG=true` is also set, printing a descriptive fatal message listing the security implications. `docker-compose.run.yml` sets `ALLOW_DEBUG: "true"` on both the `api` and `worker` services so the dev override continues to work, while any production stack that omits the file will fail fast rather than boot in insecure mode.

~~**D-1 — API Dockerfile base image unpinned by digest**~~
- ~~File: `tutor-platform-api/Dockerfile:5`~~
- ~~`FROM python:3.12-slim` lacks a `@sha256:` pin. The web image is already pinned; the API image is not, making builds non-reproducible.~~
- **Fixed 2026-05-14**: Pinned to `python:3.12-slim@sha256:401f6e1a67dad31a1bd78e9ad22d0ee0a3b52154e6bd30e90be696bb6a3d7461` (multi-arch index digest, python 3.12.13-slim-trixie, 2026-05-08). Refresh with `./scripts/pin-base-images.sh` when the image is bumped.

~~**G-6 — Review endpoint paths in spec do not match implementation**~~
- ~~File: `docs/project-spec.md §7.8` vs. `tutor-platform-api/app/review/api/router.py`~~
- ~~Spec defines `GET /api/tutors/{tutor_id}/reviews` (implemented in tutor_router.py, not review router) and `POST /api/matches/{match_id}/reviews`. Frontend following the spec will hit 404s on review creation.~~
- **Fixed 2026-05-14**: `match_reviews_router` (prefix `/api/matches`, routes `POST /{match_id}/reviews` and `GET /{match_id}/reviews`) was added to `review/api/router.py` and registered in `main.py`. `GET /api/tutors/{tutor_id}/reviews` is served by `tutor_router.py` and also registered. All four spec §7.8 paths (`GET /api/tutors/{tutor_id}/reviews`, `GET /api/matches/{match_id}/reviews`, `POST /api/matches/{match_id}/reviews`, `PATCH /api/reviews/{id}`) are live and match the spec.

~~**G-8 — Import/export/stats described as async Huey tasks; they run synchronously**~~
- ~~Files: `docs/project-spec.md §9.2`, `README.md:67,481`~~
- ~~The spec and README both assert these operations are dispatched to the Huey worker. They are not. The Huey task implementations exist but are never called from any route handler.~~
- **Fixed 2026-05-14**: `docs/project-spec.md §9.2` task table updated to distinguish between truly-async tasks (`calculate_income_stats`, `calculate_expense_stats` — dispatched to Huey by the analytics router and returning a `task_id`) and synchronous operations (`import_csv_task`, `export_csv_task`, `generate_seed_data` — Huey task definitions exist in `app/tasks/` but current admin routes call the service layer synchronously). `§9.3` polling endpoint corrected to `GET /api/stats/tasks/{task_id}`. `§9.4` worker.py code example updated to reflect actual imports and configuration. Note: stats tasks are correctly async; the audit's claim that "Huey task implementations are dead code" was accurate only for import/export/seed, not for stats.

~~**H-3 — README background-tasks table incorrectly attributes stats tasks to "Admin action" trigger**~~
- ~~File: `README.md:480–482`~~
- ~~Stats tasks are listed as triggered by "Admin action" in the README. They are actually called synchronously from analytics route handlers, and the Huey task implementations are dead code.~~
- **Fixed 2026-05-14**: README background-tasks table updated: `calculate_income_stats` trigger changed to "Tutor action (`GET /api/stats/income`)", `calculate_expense_stats` trigger changed to "Parent action (`GET /api/stats/expense`)". `import_csv_task`, `export_csv_task`, and `generate_seed_data` rows updated to note Huey task definitions exist but admin routes run synchronously. Trailing note updated from "Admin-triggered tasks" to "Stats tasks".

~~**H-4 — README claims CSV import/export runs asynchronously in the worker**~~
- ~~File: `README.md:67`~~
- ~~These operations run synchronously in FastAPI request handlers.~~
- **Fixed 2026-05-14**: `README.md` line 67 updated from "(runs asynchronously in the worker)" to "(runs synchronously in the request handler)".


2026-05-14 fixed (above)

---

### Low

**F-19 — `current_password` in `ChangePasswordRequest` has no `min_length` validator**
- File: `tutor-platform-api/app/identity/api/schemas.py:88`
- An empty string passes schema validation and reaches the bcrypt `verify_password` call.

**F-20 — `GET /api/admin/export/{table_name}` — spec requires POST**
- File: `tutor-platform-api/app/admin/api/router.py:132`
- HTTP method mismatch with spec §7.10.

**F-21 — `GET /api/admin/export-all` — spec requires POST**
- File: `tutor-platform-api/app/admin/api/router.py:399`
- HTTP method mismatch with spec §7.10.

**F-22 — `day_of_week` uses 0–6 (0=Sunday); spec defines 1–7 (1=Monday)**
- File: `tutor-platform-api/app/catalog/api/schemas.py:30`
- Spec §6.2.6 defines `day_of_week` as 1–7 with 1=Monday. The API accepts 0–6. This is a silent data mismatch that will display the wrong weekday in the frontend calendar.

**F-23 — `PostgresSubjectRepository` instantiated inline in a route handler**
- File: `tutor-platform-api/app/catalog/api/tutor_router.py:104`
- Bypasses the dependency injection pattern used everywhere else; makes unit testing harder.

**F-24 — `get_db` imported from `identity` bounded context instead of `shared`**
- File: `tutor-platform-api/app/review/api/router.py:5`
- All routers import `get_db` from `app.identity.api.dependencies`, creating an unnecessary cross-context coupling.

**F-25 — Relative `data/export` and `data/backups` paths are fragile under process managers**
- File: `tutor-platform-api/app/admin/api/router.py:146,259`
- `Path("data/export")` is relative to the process working directory, which is not guaranteed to be the project root under a process manager or in Docker.

**F-26 — `update_me` uses manual `model_fields_set` loop instead of `model_dump(exclude_unset=True)`**
- File: `tutor-platform-api/app/identity/api/router.py:182`
- All other update handlers use `model_dump(exclude_unset=True)` correctly; this one diverges and could include `None` for fields explicitly sent as `null`.

**S-1 — `idempotency_keys.match_id` has no foreign key to `matches`**
- File: `tutor-platform-api/app/init_db.py:240`
- `match_id INTEGER NOT NULL` lacks `REFERENCES matches(match_id)`. Should be `ON DELETE CASCADE` to tie key lifetime to the match.

**S-2 — `COALESCE(x, NULL)` is a no-op in tutor avg-rating query**
- File: `tutor-platform-api/app/catalog/infrastructure/postgres_tutor_repo.py:146–149`
- Likely intended as `COALESCE(r.avg_r1, 0)` to return zero for unreviewed tutors. As-is, the API returns NULL for unreviewed tutors.

**S-3 — New conversation INSERT sets `last_message_at = NOW()` instead of NULL**
- File: `tutor-platform-api/app/messaging/infrastructure/postgres_conversation_repo.py:58–60`
- Empty conversations appear at the top of the inbox sorted by `last_message_at DESC` before any message is sent.

**S-4 — `rate_limit_hits` table has no TTL column or pruning mechanism**
- File: `tutor-platform-api/app/init_db.py:254–258`
- The table accumulates indefinitely. Other auth tables (`refresh_token_blacklist`, `idempotency_keys`) have `expires_at` columns; `rate_limit_hits` does not.

**S-5 — `tutor_availability` lacks a unique constraint on `(tutor_id, day_of_week, start_time)`**
- File: `tutor-platform-api/app/init_db.py:92–99`
- The repo uses DELETE + re-INSERT (correct), but a concurrent insert or direct DB write could create duplicate availability slots without a DB-level guard.

**S-6 — No DB-level unique partial index to prevent duplicate active matches (TOCTOU)**
- File: `tutor-platform-api/app/init_db.py:120–153`
- The app-level `check_duplicate_active()` is a SELECT followed by INSERT. Two concurrent requests without an idempotency key can both pass the check and create two rows.


2026-05-14 fixed (above)


**D-1 — Seed: `terminated_by` set on directly-seeded `ended` match**
- File: `tutor-platform-api/seed/generator.py:400`
- Convention is that `terminated_by` identifies the initiator of a termination request; setting it on a directly-inserted `ended` match is inconsistent.

**D-2 — Seed: `_dt` helper creates naive (timezone-unaware) datetimes**
- File: `tutor-platform-api/seed/generator.py:43–45`
- Returns `datetime(...)` without `tzinfo`. Should either be removed (it is unused) or fixed to use `timezone.utc`.

**D-3 — Seed: conversation created with non-null `last_message_at` before any messages**
- File: `tutor-platform-api/seed/generator.py:310–315`
- Intermediate state is inconsistent with the schema's semantics (the final update corrects it, but the initial value is semantically wrong).

**Q-1 — `list_by_student_for_tutor` JOIN can return duplicate exam rows**
- File: `tutor-platform-api/app/teaching/infrastructure/postgres_exam_repo.py:56–66`
- Join on `(student_id, subject_id)` without `DISTINCT` could produce duplicates if multiple match rows satisfy the condition.

**Q-2 — `anonymize_user` active-match check omits `paused` and `terminating` statuses**
- File: `tutor-platform-api/app/admin/infrastructure/table_admin_repo.py:139`
- `WHERE status NOT IN ('ended', 'cancelled', 'rejected')` should also exclude `'paused'` and `'terminating'`, which are non-terminal states.

**Q-3 — `count_by_tutor_user_id` counts all historical matches; no status filter**
- File: `tutor-platform-api/app/matching/infrastructure/postgres_match_repo.py:87–94`
- Pagination total includes ended/cancelled matches, which inflates page count when viewing active matches.

**Q-4 — Correlated `session_count` subquery in `get_match_for_create` is fetched but never used**
- File: `tutor-platform-api/app/review/infrastructure/postgres_review_repo.py:7–16`
- The column is computed on every review creation but no business rule references it. Dead computation.

**Q-5 — `find_conversations_for_user` passes `user_id` four times as separate positional params**
- File: `tutor-platform-api/app/messaging/infrastructure/postgres_conversation_repo.py:27–45`
- Fragile tuple: future refactoring of the query must update the caller's argument count in lockstep.

**Q-6 — `has_valid_match_between` only excludes `rejected`; allows messaging after `ended`/`cancelled`**
- File: `tutor-platform-api/app/messaging/infrastructure/postgres_conversation_repo.py:85–103`
- Whether allowing messaging after an ended match is intentional is unclear from the spec.

**Q-7 — Income/expense breakdown includes sessions regardless of `visible_to_parent`**
- File: `tutor-platform-api/app/analytics/infrastructure/postgres_stats_repo.py:26–74`
- Financial totals are correct, but the breakdown may reveal the existence of hidden sessions to parents. Likely intentional; should be documented.

**Q-8 — Only router file containing raw inline SQL; bypasses repository pattern**
- File: `tutor-platform-api/app/matching/api/router.py:35–43`
- Not an injection risk (parameterized), but an architectural violation that makes this path harder to test.


2026-05-14 fixed (above)


**DOC-1 — `database-schema.md` header claims 17 tables; DDL creates 18**
- File: `docs/database-schema.md:4`

**DOC-2 — Spec lists `subjects.category` as `TEXT(20)`; DDL uses `VARCHAR(30)`**
- File: `docs/project-spec.md §6.2.4`

**DOC-3 — Spec lists `users.username` as `TEXT(50)`; DDL uses `VARCHAR(100)`**
- File: `docs/project-spec.md §6.2.1`

**DOC-4 — Spec lists `users.display_name` as `TEXT(50)`; DDL uses `VARCHAR(100)`**
- File: `docs/project-spec.md §6.2.1`

**DOC-5 — Spec §5.11 says "13 tables designed"; actual codebase has 18**
- File: `docs/project-spec.md:1276`

**SP-1 — Spec exam_type values differ from implementation constants**
- Files: `docs/project-spec.md §5.6`, `tutor-platform-api/app/teaching/domain/constants.py:9`
- Spec: "段考、模考、隨堂考". Implementation: `("段考", "小考", "模擬考", "其他")`. The spec is stale.

**SP-2 — Spec-required upsert import mode not implemented; only plain INSERT exists**
- File: `docs/project-spec.md §5.10`
- The spec describes both upsert and overwrite modes. Only overwrite (`clear_first=True`) is implemented; `ON CONFLICT DO UPDATE` is absent.


2026-05-14 fixed (above)


~~**A-3 — `worker` does not depend on `api: service_healthy`; bootstrap race possible**~~
- ~~File: `docker-compose.yml:133–135`~~
- ~~Both services run `run_bootstrap()` protected by an advisory lock, but adding `api: condition: service_healthy` would eliminate the race entirely.~~
- **Fixed 2026-05-14**: Added `api: condition: service_healthy` to the `worker` service's `depends_on` block. The worker now waits for the API healthcheck to pass before starting, eliminating the advisory-lock race window.

~~**A-4 — Conflicting healthcheck definitions in Dockerfile vs. compose**~~
- ~~Files: `docker-compose.yml:101–106`, `tutor-platform-api/Dockerfile:31–32`~~
- ~~Dockerfile has no `start_period`; compose overrides with 90s. When the image is run outside compose, the container becomes unhealthy during bootstrap.~~
- **Fixed 2026-05-14**: Added `--start-period=90s` to the `HEALTHCHECK` directive in `Dockerfile`. Both the Dockerfile and the compose override now agree on 90s start period, so the container is not marked unhealthy during initial bootstrap regardless of whether compose or bare Docker runs the image.

~~**A-5 — `FORWARDED_ALLOW_IPS` and Nginx fixed IP are coupled without automated validation**~~
- ~~File: `docker-compose.yml:84,183`~~
- ~~An edit to the subnet or web IP that does not also update `FORWARDED_ALLOW_IPS` would silently disable X-Forwarded-For trust.~~
- **Fixed 2026-05-14**: Both `FORWARDED_ALLOW_IPS` (api service environment) and `ipv4_address` (web service network) now use `${WEB_IP:-172.28.0.10}`. A single change to `WEB_IP` in `.env` propagates to both locations. `WEB_IP=172.28.0.10` added to `.env.example` with an explanatory comment.

~~**B-1 — `docker-compose.override.yml` uses `!override` tag requiring Compose v2**~~
- ~~File: `docker-compose.override.yml:14`~~
- ~~Legacy `docker-compose` v1 will fail with a YAML parse error on this tag.~~
- **Fixed 2026-05-14**: Removed the `!override` tag from `ports:` in `docker-compose.override.yml`. Since `api` has no `ports:` block in the base compose file, there is nothing to override — the plain list assignment is semantically identical on Compose v2 and parses cleanly on Compose v1.

~~**C-2 — `COOKIE_SECURE` and `CORS_ORIGINS` set on `worker` service where they have no effect**~~
- ~~File: `docker-compose.run.yml:17–20`~~
- ~~The Huey consumer never issues cookies or evaluates CORS; these variables are dead config.~~
- **Fixed 2026-05-14**: Removed `COOKIE_SECURE` and `CORS_ORIGINS` from the `worker` service's environment block in `docker-compose.run.yml`. The worker retains `DEBUG` and `ALLOW_DEBUG` (required by the entrypoint guard added in C-1).

~~**D-2 — `pip install` without `--require-hashes`; builds not fully reproducible**~~
- ~~File: `tutor-platform-api/Dockerfile:18`~~
- **Fixed 2026-05-14**: Generated `requirements.lock` via `pip-compile --generate-hashes --output-file=requirements.lock requirements.txt` (pip-tools 7.x). The lock file pins all transitive dependencies with their SHA-256 hashes covering every published platform wheel. `Dockerfile` now copies both `requirements.txt` and `requirements.lock`, installs from the lock file with `pip install --no-cache-dir --require-hashes -r requirements.lock`, and includes instructions for regenerating the lock file when `requirements.txt` changes.

~~**D-3 — `psycopg2-binary>=2.9.11` is a range constraint; all other packages use exact pins**~~
- ~~File: `tutor-platform-api/requirements.txt:9`~~
- **Fixed 2026-05-14**: Changed `psycopg2-binary>=2.9.11` to `psycopg2-binary==2.9.11`. All direct dependencies are now exact pins.

~~**E-1 — `jwt_secret_key_previous` placeholder rejection list is incomplete**~~
- ~~File: `tutor-platform-api/docker-entrypoint.sh:53–58`~~
- ~~The longer placeholder form used in `jwt_secret_key`'s list is absent from the `previous` key's list.~~
- **Fixed 2026-05-14**: Added `"REPLACE_WITH_HEX_FROM_secrets.token_hex_32_AT_LEAST_32_CHARS"` to the `jwt_secret_key_previous` `case` pattern, matching the full rejection list used for `jwt_secret_key`.

~~**F-1 — `tzdata` package missing from requirements; `zoneinfo` lookups fail on Windows/macOS local dev**~~
- ~~File: `tutor-platform-api/requirements.txt`~~
- ~~`ZoneInfo("Asia/Taipei")` will raise `ZoneInfoNotFoundError` on non-Linux dev machines without `tzdata` installed.~~
- **Fixed 2026-05-14**: Added `tzdata==2025.1` to `requirements.txt`. The `tzdata` PyPI package ships the full IANA timezone database as a pure-Python package, so `ZoneInfo("Asia/Taipei")` now works on Windows and macOS local dev without any system package installation.

**G-1 — Table count inconsistent across spec, README, and actual DDL**
- Files: `docs/project-spec.md §6.1`, `README.md:308`
- Spec: 13 tables. README: 17 (14 business + 3 support). Actual: 18 (13 business + 5 support). Three different numbers.

**G-2 — `password_history` table not documented in spec field-definition section**
- File: `docs/project-spec.md §6.2`

**G-3 — `DELETE /api/students/{id}` implemented but missing from spec**
- File: `docs/project-spec.md §7.3`

**G-4 — `GET /api/tutors/me` implemented but missing from spec**
- File: `docs/project-spec.md §7.2`

**G-5 — `PUT /api/tutors/profile/subjects` implemented but missing from spec**
- File: `docs/project-spec.md §7.2`

**G-7 — Spec says all 13 tables are exportable; `users` is explicitly blocked**
- File: `docs/project-spec.md §5.10`
- The exclusion is the correct security decision, but the spec is misleading.

**G-9 — Spec requires `POST /api/admin/export-all`; implementation uses `GET`**
- File: `docs/project-spec.md §7.10`

**G-10 — Spec shows single-step `POST /api/admin/reset`; implementation uses two-step flow**
- File: `docs/project-spec.md §7.10`

**G-11 — Admin endpoints not in the spec: `/tables`, `/users/{id}/anonymize`, `/users/{id}/reset-password`**
- File: `tutor-platform-api/app/admin/api/router.py`

**G-12 — Parent dashboard "recent sessions feed" has no dedicated cross-match endpoint**
- File: `docs/project-spec.md §5.8`
- Spec §5.8 describes a parent dashboard showing recent sessions across all children. No such aggregate endpoint exists; the frontend would need N calls for N active matches.

**G-13 — Stats tasks described as "scheduled"; no `@huey.periodic_task` registration exists**
- Files: `docs/project-spec.md §9.2`, `tutor-platform-api/app/tasks/stats_tasks.py`
- `calculate_income_stats` and `calculate_expense_stats` are `@huey.task()` (on-demand only), not periodic tasks.

**G-14 — `GET /api/stats/student-progress/{id}` restricted to parent+admin; spec says match participants (includes tutors)**
- File: `tutor-platform-api/app/analytics/api/router.py:78`

**H-1 — README table count wrong (says 17/14/3; actual is 18/13/5)**
- File: `README.md:308–310`

**H-2 — README Swagger UI access condition is slightly misleading**
- File: `README.md:141`
- `ENABLE_DOCS=true` is the primary gate; `DEBUG=true` is enforced as a prerequisite by config validation, not an independent toggle.

**H-5 — Frontend local dev port listed as 5273 in README; Vite default is 5173**
- File: `README.md:205`

**SEC-3 — `register` endpoint returns 201; `login` returns 200 — status code contract inconsistency**
- File: `tutor-platform-api/app/identity/api/router.py:59`

**SEC-16 — `is_admin()` is a plain function, not a FastAPI dependency**
- File: `tutor-platform-api/app/identity/api/dependencies.py:34`
- No mechanism prevents a future caller from passing an unverified dict.

**SEC-19 — `.env.docker` (committed dev file) ships `ADMIN_USERNAME=owner_change_me`**
- File: `tutor-platform-api/.env.docker`
- Config validator only rejects this placeholder when `DEBUG=false`, so it would pass in a `DEBUG=true` deployment.

**SEC-20 — Real secret files on disk alongside example files**
- Files: `secrets/jwt_secret_key.txt`, `secrets/admin_password.txt`
- Gitignored but exposed by non-git sharing (zip, shared drive, `git add -f`).

**SEC-22 — Global rate-limit patch in conftest means no test exercises real bucket logic**
- File: `tutor-platform-api/tests/conftest.py:46`

**SEC-23 — IP-based rate limiting is weak under NAT/shared proxies**
- File: `tutor-platform-api/app/middleware/rate_limit.py`
- Known by-design limitation; noted for awareness.

---

## Section 2 — Consolidated Master Index

| ID | Severity | Module | File (approx. line) | Issue |
|----|----------|--------|---------------------|-------|
| F-01 | **Critical** | Review | `review_service.py:27` | Reviews allowed on active/paused matches; spec requires `ended` only |
| F-02 | **Critical** | Matching | `matching/api/router.py:36–67` | Idempotency key double-commit / transaction ordering hazard |
| F-03 | **High** | Teaching | `session_router.py:21,47` | Session routes flat; spec requires nested under `/api/matches/{id}/sessions` |
| F-04 | **High** | Teaching | `exam_router.py:21,35` | Exam routes flat; spec requires nested under `/api/students/{id}/exams` |
| F-05 | **High** | Review | `review/api/router.py:25,35` | Review create/list flat; spec requires nested under `/api/matches/{id}/reviews` |
| F-06 | **High** | Admin | `admin/api/router.py:165,181` | Admin reset two-step flow; spec and frontend expect single-step `POST /api/admin/reset` |
| F-07 | **High** | Admin | `admin/api/router.py:102` | Import uses `POST /api/admin/import?table_name=`; spec defines path parameter |
| F-08 | **High** | Catalog | `student_router.py:17` | `GET /api/students` rejects tutors; spec allows tutors to list their matched students |
| F-09 | **High** | Catalog | `tutor_router.py:47` | Tutor search has no role restriction; spec prohibits tutors from searching tutors |
| F-10 | **High** | Matching | `match_app_service.py:131–138` | Unlocked `find_by_id` before transaction creates TOCTOU on status/role flags |
| SEC-4 | **High** | Tests | `test_auth.py:35,54` | Register tests assert 200 but route returns 201 — always fail |
| SEC-5 | **High** | Tests | `test_auth.py:116–117` | Login test asserts `access_token` in response body; tokens now in cookies |
| SEC-7 | **High** | Tests | — | Zero coverage: students, tutors, subjects, messaging, analytics, exams |
| SEC-8 | **High** | Tests | — | Admin reset flow has zero tests |
| SEC-9 | **High** | Tests | `admin/api/router.py` | Admin import/export endpoints have zero tests |
| F-11 | Medium | Catalog | `subject_router.py:11` | `GET /api/subjects` unauthenticated — undocumented design decision |
| F-12 | Medium | Review | `review/api/schemas.py:52–78` | `ReviewUpdate` can nullify mandatory `parent_to_tutor` rating axes |
| F-13 | Medium | Teaching | `session_router.py:82` | `DELETE /api/sessions/{id}` exists but absent from spec |
| F-14 | Medium | Matching | `matching/api/router.py:72` | `GET /api/matches` missing `status` filter documented in spec |
| F-15 | Medium | Review | `review_service.py:78–127` | `update_review` does not prevent nullifying mandatory rating axes |
| F-16 | Medium | Admin | `admin/api/router.py:425` | `import-all` reads ZIP without size cap |
| F-17 | Medium | Domain | `value_objects.py:85` | `Contract` allows `hourly_rate=0`; API requires `>= 1` |
| F-18 | Medium | Analytics | `analytics/api/router.py:41,54` | Stats compute synchronously; spec requires background task dispatch |
| SEC-1 | Medium | Security | `middleware/request_id.py:10` | Client `X-Request-ID` not sanitized — log injection risk |
| SEC-2 | Medium | Auth | `main.py:177–189` | Access tokens not blacklisted after admin-forced password reset |
| SEC-6 | Medium | Tests | `test_auth.py:113–117` | Login test does not verify cookie delivery (HttpOnly, SameSite, Secure) |
| SEC-10 | Medium | Tests | `test_auth.py` | `PUT /api/auth/me` has zero tests; CSRF requirement unverified |
| SEC-11 | Medium | Tests | `test_sql_injection.py` | SQL injection tests miss comment/session/message free-text fields |
| SEC-12 | Medium | Tests | `test_middleware.py` | No test asserts `_CSRF_EXEMPT_PATHS` membership as a security invariant |
| SEC-13 | Medium | Tests | — | Admin read endpoints (system-status, tables, users list) have zero tests |
| SEC-14 | Medium | Tests | `admin/api/router.py:439` | `GET /api/admin/tasks/{task_id}` no-pickle invariant is untested |
| SEC-15 | Medium | Auth | `tutor_router.py:47` | Tutor search requires auth; inconsistent with public subjects |
| SEC-17 | Medium | Config | `.env.example:24` | Admin password requirement documented incorrectly (12 chars vs enforced 16) |
| SEC-18 | Medium | Config | `.env.docker.example:32–35` | HTTP CORS + `COOKIE_SECURE=true` combination is unusable |
| SEC-21 | Medium | Security | `admin/api/router.py:414` | `import-all` skips Content-Type validation that single-CSV import performs |
| ~~A-1~~ | ~~Medium~~ | ~~Infra~~ | ~~`docker-compose.yml:49`~~ | ~~`pg_isready -U ${DB_USER}` env var may not expand in CMD-SHELL~~ — **Fixed 2026-05-14** |
| ~~A-2~~ | ~~Medium~~ | ~~Infra~~ | ~~`docker-compose.yml:160–191`~~ | ~~`web` (Nginx) service has no healthcheck~~ — **Fixed 2026-05-14** |
| ~~C-1~~ | ~~Medium~~ | ~~Infra~~ | ~~`docker-compose.run.yml:9–20`~~ | ~~`DEBUG=true`+`COOKIE_SECURE=false` committed with no production guard~~ — **Fixed 2026-05-14** |
| ~~D-1~~ | ~~Medium~~ | ~~Infra~~ | ~~`Dockerfile:5`~~ | ~~API base image `python:3.12-slim` unpinned by digest~~ — **Fixed 2026-05-14** |
| ~~G-6~~ | ~~Medium~~ | ~~Spec~~ | ~~`project-spec.md §7.8`~~ | ~~Review endpoint paths differ between spec and implementation~~ — **Fixed 2026-05-14** |
| ~~G-8~~ | ~~Medium~~ | ~~Spec~~ | ~~`project-spec.md §9.2`~~ | ~~Import/export/stats described as async Huey tasks; they run synchronously~~ — **Fixed 2026-05-14** |
| ~~H-3~~ | ~~Medium~~ | ~~Docs~~ | ~~`README.md:480–482`~~ | ~~Stats tasks incorrectly described as "Admin action" triggered~~ — **Fixed 2026-05-14** |
| ~~H-4~~ | ~~Medium~~ | ~~Docs~~ | ~~`README.md:67`~~ | ~~CSV import/export incorrectly described as running async in the worker~~ — **Fixed 2026-05-14** |
| F-19 | Low | Identity | `schemas.py:88` | `current_password` has no `min_length` validator |
| F-20 | Low | Admin | `admin/api/router.py:132` | `GET /api/admin/export/{table}` — spec requires POST |
| F-21 | Low | Admin | `admin/api/router.py:399` | `GET /api/admin/export-all` — spec requires POST |
| F-22 | Low | Catalog | `schemas.py:30` | `day_of_week` 0–6 vs. spec 1–7; silent calendar off-by-one |
| F-23 | Low | Catalog | `tutor_router.py:104` | `PostgresSubjectRepository` instantiated inline, bypassing DI |
| F-24 | Low | Review | `review/api/router.py:5` | `get_db` imported from `identity` BC instead of `shared` |
| F-25 | Low | Admin | `admin/api/router.py:146,259` | Relative `data/export` and `data/backups` paths fragile under process managers |
| F-26 | Low | Identity | `identity/api/router.py:182` | `update_me` uses manual `model_fields_set` loop instead of `model_dump(exclude_unset=True)` |
| S-1 | Low | DB | `init_db.py:240` | `idempotency_keys.match_id` has no FK to `matches` |
| S-2 | Low | DB | `postgres_tutor_repo.py:146–149` | `COALESCE(x, NULL)` is a no-op; should be `COALESCE(x, 0)` |
| S-3 | Low | DB | `postgres_conversation_repo.py:58–60` | New conversation INSERT sets `last_message_at = NOW()` instead of NULL |
| S-4 | Low | DB | `init_db.py:254–258` | `rate_limit_hits` has no TTL or pruning mechanism |
| S-5 | Low | DB | `init_db.py:92–99` | `tutor_availability` lacks unique constraint on `(tutor_id, day_of_week, start_time)` |
| S-6 | Low | DB | `init_db.py:120–153` | No DB-level partial unique index to prevent duplicate active matches |
| D-1 | Low | Seed | `generator.py:400` | `terminated_by` set on directly-seeded `ended` match |
| D-2 | Low | Seed | `generator.py:43–45` | `_dt` helper creates naive datetimes; unused but unfixed |
| D-3 | Low | Seed | `generator.py:310–315` | Conversation `last_message_at` set to non-null before any messages |
| Q-1 | Low | SQL | `postgres_exam_repo.py:56–66` | `list_by_student_for_tutor` JOIN can produce duplicate exam rows |
| Q-2 | Low | SQL | `table_admin_repo.py:139` | `anonymize_user` check misses `paused` and `terminating` statuses |
| Q-3 | Low | SQL | `postgres_match_repo.py:87–94` | Pagination total counts all historical matches; no status filter |
| Q-4 | Low | SQL | `postgres_review_repo.py:7–16` | Correlated `session_count` subquery fetched but never used |
| Q-5 | Low | SQL | `postgres_conversation_repo.py:27–45` | `user_id` bound four times as separate positional params |
| Q-6 | Low | SQL | `postgres_conversation_repo.py:85–103` | `has_valid_match_between` allows messaging after `ended`/`cancelled` matches |
| Q-7 | Low | SQL | `postgres_stats_repo.py:26–74` | Expense/income stats include hidden sessions in parent's breakdown |
| Q-8 | Low | SQL | `matching/api/router.py:35–43` | Only router file with raw inline SQL; bypasses repository pattern |
| DOC-1 | Low | Docs | `database-schema.md:4` | Header claims 17 tables; DDL creates 18 |
| DOC-2 | Low | Docs | `project-spec.md §6.2.4` | Spec says `category TEXT(20)`; DDL has `VARCHAR(30)` |
| DOC-3 | Low | Docs | `project-spec.md §6.2.1` | Spec says `username TEXT(50)`; DDL has `VARCHAR(100)` |
| DOC-4 | Low | Docs | `project-spec.md §6.2.1` | Spec says `display_name TEXT(50)`; DDL has `VARCHAR(100)` |
| DOC-5 | Low | Docs | `project-spec.md:1276` | Spec says 13 tables; actual is 18 |
| SP-1 | Low | Spec | `project-spec.md §5.6` | Spec exam_type values differ from implementation constants |
| SP-2 | Low | Spec | `project-spec.md §5.10` | Spec-required upsert import mode not implemented |
| ~~A-3~~ | ~~Low~~ | ~~Infra~~ | ~~`docker-compose.yml:133–135`~~ | ~~`worker` does not depend on `api: service_healthy`; bootstrap race possible~~ — **Fixed 2026-05-14** |
| ~~A-4~~ | ~~Low~~ | ~~Infra~~ | ~~`docker-compose.yml:101–106`~~ | ~~Conflicting healthcheck definitions in Dockerfile vs. compose~~ — **Fixed 2026-05-14** |
| ~~A-5~~ | ~~Low~~ | ~~Infra~~ | ~~`docker-compose.yml:84,183`~~ | ~~`FORWARDED_ALLOW_IPS` and Nginx fixed IP coupled without automated validation~~ — **Fixed 2026-05-14** |
| ~~B-1~~ | ~~Low~~ | ~~Infra~~ | ~~`docker-compose.override.yml:14`~~ | ~~`!override` tag requires Compose v2; v1 users get a parse error~~ — **Fixed 2026-05-14** |
| ~~C-2~~ | ~~Low~~ | ~~Infra~~ | ~~`docker-compose.run.yml:17–20`~~ | ~~`COOKIE_SECURE`/`CORS_ORIGINS` set on `worker` where they have no effect~~ — **Fixed 2026-05-14** |
| ~~D-2~~ | ~~Low~~ | ~~Infra~~ | ~~`Dockerfile:18`~~ | ~~`pip install` without `--require-hashes`; builds not reproducible~~ — **Fixed 2026-05-14** |
| ~~D-3~~ | ~~Low~~ | ~~Infra~~ | ~~`requirements.txt:9`~~ | ~~`psycopg2-binary>=2.9.11` is a range; all others use exact pins~~ — **Fixed 2026-05-14** |
| ~~E-1~~ | ~~Low~~ | ~~Infra~~ | ~~`docker-entrypoint.sh:53–58`~~ | ~~`jwt_secret_key_previous` placeholder rejection list incomplete~~ — **Fixed 2026-05-14** |
| ~~F-1~~ | ~~Low~~ | ~~Infra~~ | ~~`requirements.txt`~~ | ~~`tzdata` missing; `ZoneInfo("Asia/Taipei")` fails on Windows/macOS dev~~ — **Fixed 2026-05-14** |
| G-1 | Low | Docs | `project-spec.md §6.1`, `README.md:308` | Table count inconsistent: spec 13, README 17, actual 18 |
| G-2 | Low | Docs | `project-spec.md §6.2` | `password_history` table not documented in spec |
| G-3 | Low | Docs | `project-spec.md §7.3` | `DELETE /api/students/{id}` implemented but missing from spec |
| G-4 | Low | Docs | `project-spec.md §7.2` | `GET /api/tutors/me` implemented but missing from spec |
| G-5 | Low | Docs | `project-spec.md §7.2` | `PUT /api/tutors/profile/subjects` implemented but missing from spec |
| G-7 | Low | Docs | `project-spec.md §5.10` | Spec says all 13 tables exportable; `users` is blocked |
| G-9 | Low | Docs | `project-spec.md §7.10` | Spec requires `POST /api/admin/export-all`; implementation uses `GET` |
| G-10 | Low | Docs | `project-spec.md §7.10` | Spec shows single-step reset; implementation uses two-step at different paths |
| G-11 | Low | Docs | `admin/api/router.py` | Admin endpoints `/tables`, `/anonymize`, `/reset-password` not in spec |
| G-12 | Low | Docs | `project-spec.md §5.8` | Parent dashboard "recent sessions feed" has no aggregate endpoint |
| G-13 | Low | Docs | `project-spec.md §9.2` | Stats tasks described as "scheduled"; no `@huey.periodic_task` registered |
| G-14 | Low | Docs | `analytics/api/router.py:78` | Student-progress restricted to parent+admin; spec says match participants |
| H-1 | Low | Docs | `README.md:308–310` | README table count wrong (17/14/3 vs actual 18/13/5) |
| H-2 | Low | Docs | `README.md:141` | Swagger UI access condition description slightly misleading |
| H-5 | Low | Docs | `README.md:205` | Frontend local dev port listed as 5273; Vite default is 5173 |
| SEC-3 | Low | Auth | `identity/api/router.py:59` | Minor status code inconsistency: register 201, login 200 |
| SEC-16 | Low | Auth | `identity/api/dependencies.py:34` | `is_admin()` is a plain function, not a FastAPI dependency |
| SEC-19 | Low | Config | `.env.docker` | `ADMIN_USERNAME=owner_change_me` passes validation when `DEBUG=true` |
| SEC-20 | Low | Config | `secrets/` | Real secret files on disk; protected by `.gitignore` but not other sharing |
| SEC-22 | Low | Tests | `tests/conftest.py:46` | Global rate-limit patch; real bucket logic never exercised in tests |
| SEC-23 | Low | Infra | `middleware/rate_limit.py` | IP-based bucketing weak under NAT/shared proxies (by-design limitation) |
