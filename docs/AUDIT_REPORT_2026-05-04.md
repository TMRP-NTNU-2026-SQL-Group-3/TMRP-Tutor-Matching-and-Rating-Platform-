# TMRP Full-Stack Audit Report

**Project:** Tutor Matching and Rating Platform (TMRP)  
**Date:** 2026-05-04  
**Auditors:** Multi-agent automated review (API Security, API Quality, Frontend, Infrastructure)  
**Scope:** All source files — `tutor-platform-api/`, `tutor-platform-web/`, `docker-compose*.yml`, `scripts/`, `secrets/`

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [API — Security Vulnerabilities](#2-api--security-vulnerabilities)
3. [API — Systemic Bugs & Responsibility Violations](#3-api--systemic-bugs--responsibility-violations)
4. [Frontend — Security, Bugs & Responsibility](#4-frontend--security-bugs--responsibility)
5. [Infrastructure — Docker, Secrets & Database Schema](#5-infrastructure--docker-secrets--database-schema)
6. [Consolidated Severity Index](#6-consolidated-severity-index)
7. [What the Codebase Does Well](#7-what-the-codebase-does-well)

---

## 1. Executive Summary

Four independent audits were conducted in parallel covering the Python FastAPI backend (130+ files), the Vue 3 frontend (all `src/` files plus nginx/Vite config), and the infrastructure layer (Docker Compose, secrets management, database schema, CI scripts, and tests).

**Highest-priority findings:**

| # | Severity | Location | Summary |
|---|----------|----------|---------|
| I-01 | **Critical** | `docker-compose.yml:92` | API port 8000 exposed on all interfaces in production |
| I-02 | **High** | `secrets/admin_password.txt` | Admin password fails the 4-character-class validator — app cannot start |
| HIGH-1 | **High** | `matching/application/match_app_service.py:131` | TOCTOU: permission check on unlocked pre-flight read, state write under lock |
| DATA-1 | **High** | `matching/application/match_app_service.py:172` | TERMINATE branch does not lock the match row before writing |
| ERR-1 | **High** | `matching/application/match_app_service.py:184` | `ValueError` from stale `previous_status_before_terminating` propagates as an unhandled 500 |
| BUG-01 | **High** | `views/tutor/MatchDetailView.vue:589` | `window.confirm` used inconsistently; one of six destructive actions bypasses app dialog |

**Counts by severity:**

| Severity | Count |
|----------|-------|
| Critical / High | 7 |
| Medium | 22 |
| Low | 30+ |
| Informational | 5 |

---

## 2. API — Security Vulnerabilities

> **Auditor note:** No SQL injection was found anywhere. All queries use psycopg2 `%s` parameterisation; dynamic identifiers use `psql.Identifier`; LIKE inputs are escaped via `escape_like()`. The rate-limiting, CSRF, JWT, and bcrypt implementations are all sound.

---

### 2.1 Authentication & Authorization

#### HIGH-1 — TOCTOU: Permission Check on Unlocked Pre-flight Read

**File:** `app/matching/application/match_app_service.py:131`

`update_status` calls `find_by_id` (unlocked) at line 131, derives `is_parent`, `is_tutor`, and `old_status` from this snapshot, then re-enters `find_by_id_for_update` only inside the `with self._uow.begin()` block for some branches. For `TERMINATE`, `DISAGREE_TERMINATE`, `CONFIRM_TRIAL`, and `RESUME`, the permission decision is never refreshed from the locked row.

If `matches.parent_user_id` changes between the two reads (e.g., via `trg_students_propagate_parent`), the permission check is evaluated against stale data while the write uses fresh data.

**Fix:** Perform `find_by_id_for_update` first inside every branch's transaction block, then derive `is_parent`/`is_tutor` from the locked `fresh` result.

---

#### MEDIUM-AUTH-2 — Admin Reset `confirm_reset`: Password Re-verification Outside Transaction

**File:** `app/admin/api/router.py:226`

The `SELECT password_hash` and the subsequent `service.reset_database()` are not in a single transaction. A concurrent `PUT /api/auth/password` could commit a new hash in the window between the hash read and the reset, causing the reset to proceed against an already-passed comparison.

**Fix:** Wrap both steps in `with transaction(conn):` using `SELECT ... FOR UPDATE`.

---

#### MEDIUM-AUTH-3 — In-Process Idempotency Cache Not Shared Across Workers

**File:** `app/matching/api/router.py:27`

`_idempotency_cache` is a module-level `dict`. With `--workers 4`, the same `Idempotency-Key` landing on different workers sees an empty cache each time, allowing up to four duplicate match rows until the DB UNIQUE constraint fires.

**Fix:** Move idempotency state to PostgreSQL (`idempotency_keys` table) or Redis, matching the rate-limiting migration pattern.

---

#### LOW-AUTH-4 — Background Tasks Bypass HTTP-Layer Admin Role Check

**File:** `app/tasks/import_export.py:25`

`export_csv_task` and `import_csv_task` validate the table name against `ALLOWED_TABLES` but do not verify that the enqueuing context was an admin user. Direct writes to `data/huey.db` could enqueue tasks without going through the HTTP auth layer.

**Fix:** Accept and verify an `admin_user_id` parameter inside the task; restrict file permissions on `data/huey.db` to the application user (`chmod 600`).

---

#### LOW-AUTH-5 — Exam Ownership vs. Existence Distinguishable via 403/404

**File:** `app/teaching/api/exam_router.py:77`

`delete_exam` and `update_exam` return 404 if the exam does not exist, but 403 if it exists and is owned by someone else. This allows enumeration of valid `exam_id` values.

**Fix:** Return 404 in both cases (as `session_router.py:63` already does for sessions).

---

### 2.2 Input Validation Gaps

#### MEDIUM-VAL-1 — `TutorProfileUpdate.max_students` Has No Bounds

**File:** `app/catalog/api/schemas.py:12`

The column is `SMALLINT`. A value of `0` silences the capacity gate entirely; `-1` allows infinite students; values above 32,767 cause a psycopg2 `DataError` (500).

**Fix:**
```python
max_students: int | None = Field(default=None, ge=1, le=100)
```

---

#### LOW-VAL-2, 3, 4 — Missing `max_length` on Several Free-Text Fields

| Field | File | DB Column Limit |
|---|---|---|
| `SessionCreate.content_summary`, `homework`, `student_performance`, `next_plan` | `teaching/api/schemas.py:28` | TEXT (unbounded) |
| `StudentCreate.school` | `catalog/api/schemas.py:62` | VARCHAR(50) |
| `StudentCreate.grade` | `catalog/api/schemas.py:64` | VARCHAR(20) |
| `RegisterRequest.display_name` | `identity/api/schemas.py:17` | VARCHAR(100) |

Without Pydantic-side `max_length`, values exceeding the DB column length produce a psycopg2 `DataError` (500) rather than a clean 422 response.

**Fix:** Add `max_length=` matching each column's DB definition.

2026-05-05 DONE (above)

---

### 2.3 Sensitive Data Exposure

#### MEDIUM-SENS-1 — Pre-Reset Backup Path Logged to Structured Log

**File:** `app/admin/api/router.py:257`

The backup ZIP file (containing the `users` table with `password_hash`) is written to `data/backups/pre-reset-{jti}.zip`. The full path is emitted in the structured log. If logs are shipped to a third-party aggregator, anyone with log access can derive the exact path to a credential dump.

**Fix:** Log only `backup_created=True`; never log the file path.

---

#### LOW-SENS-2 — `find_detail` Returns `email` and `phone` Without Visibility Flags

**File:** `app/catalog/infrastructure/postgres_tutor_repo.py:165`

`find_detail` joins `u.email, u.phone` and returns them to the caller. `TutorService.apply_visibility` applies flags for university, department, grade_year, hourly_rate, and subjects — but not for phone or email, so contact data is always exposed.

**Fix:** Add `show_phone` and `show_email` visibility flags and apply them in `apply_visibility`, or remove contact fields from the public detail endpoint entirely.

---

### 2.4 Race Conditions

#### LOW-RACE-2 — `update_me` Read-Then-Write Without Row Lock

**File:** `app/identity/domain/services.py:154`

Two concurrent `PUT /api/auth/me` requests can both read the same user state and write conflicting updates, with the last write silently overwriting the first.

**Fix:** Wrap both the update and the subsequent read in a single transaction with `SELECT ... FOR UPDATE`, or return only the fields just written.

---

### 2.5 Insecure Defaults

#### MEDIUM-DEF-1 — `cookie_secure` Defaults to `False`

**File:** `app/shared/infrastructure/config.py:88`

The production validator blocks `cookie_secure=False` when `debug=False`, but staging environments that set `debug=True` are silently insecure — cookies are sent in cleartext on non-loopback addresses.

**Fix:** Default `cookie_secure=True`; require explicit `COOKIE_SECURE=false` for local development.

---

#### LOW-DEF-2 — No Warning When `LOG_LEVEL=DEBUG` in Non-Debug Mode

**File:** `app/shared/infrastructure/config.py`

An operator can set `LOG_LEVEL=DEBUG` in production with no startup warning.

**Fix:** Emit `logger.warning(...)` when `log_level.upper() == "DEBUG" and not self.debug`.

---

#### LOW-DEF-3 — `data/huey.db` File Permissions Depend on OS umask

**File:** `app/worker.py:10`

A default umask of `022` produces a world-readable SQLite task queue file containing task payloads (CSV content, admin user IDs).

**Fix:** Add `chmod 600 data/huey.db` to the Dockerfile/docker-compose startup; mount `data/` with restricted permissions.


2026-05-05 DONE (above)

---

### 2.6 Broken Access Control

#### MEDIUM-BAC-1 — Session List Accessible to Ex-Participants After Match Cancellation

**File:** `app/teaching/application/session_service.py:80`

`list_for_match` checks only participant membership, not match status. A tutor or parent whose match was rejected can still read all historical session logs.

**Fix:** Add a match-status check, or document as intentional retention policy.

---

#### MEDIUM-BAC-2 — No Per-Parent Student Limit

**File:** `app/catalog/api/student_router.py:40`

A parent can create unlimited student records, inflating the database and holding a tutor's capacity slots.

**Fix:** Add a pre-insert count check (e.g., reject if `COUNT(*) > 20` for this parent).

---

#### LOW-BAC-3 — Edit Logs Expose Hidden Fields to Match Parent

**File:** `app/teaching/application/session_service.py:141`

`GET /api/sessions/{id}/edit-logs` is accessible to parents, but edit logs include `old_value`/`new_value` for `student_performance` and `next_plan`, which are normally gated by `visible_to_parent=FALSE`.

**Fix:** Filter edit logs for parent viewers to only include edits of fields they would see normally, or restrict the endpoint to tutors/admins.

---

### 2.7 Rate Limiting Gaps

#### MEDIUM-RATE-1 — Tutor Review Endpoint Under Default 60/min Bucket

**File:** `app/catalog/api/tutor_router.py:165`

An authenticated user can scrape all reviews at 60 req/min.

**Fix:** Add `"/api/tutors": (30, 60)` to `RATE_LIMITS`.

---

#### LOW-RATE-2 — Profile Update Endpoints on Default Bucket

**File:** `app/middleware/rate_limit.py`

`PUT /api/auth/me` and `PUT /api/tutors/profile` can be called 60 times/min.

**Fix:** Add `"/api/auth/me": (10, 60)` and `"/api/tutors/profile": (10, 60)`.

---

### 2.8 Dependency Issues

#### LOW-DEP-1 — Private psycopg2 Pool Attributes Accessed Without Guard

**File:** `app/shared/infrastructure/database.py:94`

`pool_stats()` accesses `p._used`, `p._pool`, `p._lock` — private attributes that could be renamed in a psycopg2 minor release.

**Fix:** Wrap `pool_stats` body in `try/except AttributeError` with a fallback.

---

### 2.9 Informational

| ID | File | Issue |
|---|---|---|
| INFO-1 | `tasks/stats_tasks.py:25` | Naive `datetime.now()` (no timezone) in year range check |
| INFO-2 | `middleware/access_log.py:47` | `request.client.host` without null guard — raises `AttributeError` on some proxy configs |
| INFO-4 | `matching/api/router.py:28` | Unbounded `_idempotency_cache`; grows without LRU eviction over a 24-hour window |


2026-05-05 DONE (above)

---

## 3. API — Systemic Bugs & Responsibility Violations

### 3.1 Bugs

#### BUG-1 (High) — `update_status`: Stale Pre-flight Read Used for Permission Check in Non-trivial Branches

**File:** `app/matching/application/match_app_service.py:131`

Same root cause as HIGH-1 above. The unlocked snapshot at line 131 drives `is_parent`, `is_tutor`, and the initial `old_status` fed to the audit log. For `TERMINATE` and `DISAGREE_TERMINATE`, the locked `fresh` row is never consulted for the permission decision. See [HIGH-1](#high-1--toctou-permission-check-on-unlocked-pre-flight-read) for full analysis.

---

#### BUG-2 (High) — `CONFIRM_TRIAL` Capacity Re-check Uses `new_status` from Stale Snapshot

**File:** `app/matching/application/match_app_service.py:195`

`new_status` (computed by `resolve_transition` at line 149 against the unlocked snapshot) is used at line 222 to gate the capacity check. If a concurrent `REJECT_TRIAL` commits between the outer read and the locked block, `confirm_trial_with_terms` is invoked on an already-rejected match. The DB guard (`AND status = 'trial'`) catches the final write but only after acquiring the tutor row lock unnecessarily and returning an opaque `InvalidTransitionError`.

**Fix:** Inside the `CONFIRM_TRIAL` locked block, acquire `find_by_id_for_update` first, then re-run `resolve_transition` from the locked state.

---

#### BUG-3 (Medium) — `pg_try_advisory_xact_lock` Released Before Destructive Reset Executes

**File:** `app/admin/api/router.py:193`

`pg_try_advisory_xact_lock` is transaction-scoped and released when the transaction that acquired it ends. `service.reset_database()` uses a different connection — the advisory lock does not span connections. Two concurrent admin resets can both acquire the lock on separate connections and execute simultaneously.

**Fix:** Wrap lock acquisition, JTI burn, password re-verification, and the reset call in a single `with transaction(conn):` block so the lock is held through completion.

---

#### BUG-4 (Medium) — `SessionAppService.update` Permission Check Uses Unprotected Pre-flight Read

**File:** `app/teaching/application/session_service.py:96`

`get_match_for_create` at line 99 is called without a lock. The permission check (`match["tutor_user_id"] != tutor_user_id`) at lines 100–101 uses the unlocked result. Only inside `uow.begin()` is `get_by_id_for_update` called, but it never re-fetches the match.

**Fix:** Begin the UoW block first, acquire both `get_by_id_for_update` and the match (or include match ownership in the FOR UPDATE row), then run checks against locked data.

---

#### BUG-5 (Medium) — `send_message` Uses Wrong REST URL Structure

**File:** `app/messaging/api/router.py:63`

`POST /api/messages/conversations/{conversation_id}` sends a message *within* a conversation but hits the same URL as `GET /api/messages/conversations/{conversation_id}` which retrieves messages. This violates REST resource modelling.

**Fix:** Change the route to `POST /api/messages/conversations/{conversation_id}/messages` (status 201).

---

#### BUG-6 (Low) — `record_admin_action` Auto-commits Outside Transaction

**File:** `app/admin/infrastructure/table_admin_repo.py:201`

`BaseRepository.execute` auto-commits when `_in_transaction()` is `False`. The admin router then calls `repo.conn.commit()` again, committing an empty transaction. If `record_admin_action` fails after the preceding UPDATE succeeds, the audit trail is silently lost.

**Fix:** Wrap the operation and `record_admin_action` in a single `with transaction(conn):` block; remove the raw `conn.commit()` calls from the router.

---

#### BUG-7 (Low) — `PostgresReviewRepository.find_existing` Defined but Never Called

**File:** `app/review/infrastructure/postgres_review_repo.py:18`

The method implies a racy check-then-insert pattern that was superseded by the DB unique-index approach. Its presence may lead a future developer to accidentally use it.

**Fix:** Remove `find_existing`.

---

### 3.2 SRP Violations

#### SRP-1 (Medium) — `exam_router.py` Contains Business Logic Without a Service Layer

**File:** `app/teaching/api/exam_router.py:26`

`create_exam` and `list_exams` embed role-to-permission mapping, active-match checks, and permission errors directly in the router, reaching straight into the repository with no intermediate service.

**Fix:** Create `app/teaching/application/exam_service.py` with CRUD methods that own business rules; the router extracts parameters and returns `ApiResponse`.

---

#### SRP-2 (Medium) — `review/api/router.py` Contains Business Logic

**File:** `app/review/api/router.py:42`

`create_review` handles participant membership, review-type-role invariants, and `UniqueViolation` at the router layer. `update_review` implements lock-window calculation and timezone handling inline.

**Fix:** Create `app/review/application/review_service.py`.

---

#### SRP-3 (Low) — Admin Router Calls `conn.commit()` / `conn.rollback()` Directly

**File:** `app/admin/api/router.py:75, 323, 350`

Transaction lifecycle management belongs in infrastructure (context managers or repository methods), not in routers.

**Fix:** Use `with transaction(repo.conn):` and delegate commit/rollback away from the router.

---

#### SRP-4 (Low) — `SessionAppService` Imports Rate-Limiting Infrastructure

**File:** `app/teaching/application/session_service.py:9`

`check_and_record_bucket` is a middleware/edge concern imported into an application service, breaking the clean dependency hierarchy and making the service hard to test in isolation.

**Fix:** Move the per-match rate-limit check into `session_router.py` before calling the service.

---

### 3.3 Error Handling Gaps

#### ERR-1 (High) — `ValueError` from `previous_status_before_terminating` Propagates as Unhandled 500

**File:** `app/matching/application/match_app_service.py:184`

`previous_status_before_terminating` raises `ValueError` for malformed `termination_reason` values (e.g., imported via CSV). This is not caught in `update_status`, producing an opaque 500 indistinguishable from an infrastructure failure.

**Fix:** Catch `ValueError` and re-raise as `InvalidTransitionError` with a descriptive message; log at `ERROR` level with `match_id`.

---

#### ERR-2 (Medium) — Raw `conn.commit()` in Admin Router Obscures Failed Audit Logging

**File:** `app/admin/api/router.py:323`

If `record_admin_action` raises and is not caught, the subsequent `conn.commit()` is never reached and the exception propagates silently to the 500 handler — the audit trail is lost with no specific error returned. See also [BUG-6](#bug-6-low--record_admin_action-auto-commits-outside-transaction).

---

#### ERR-3 (Medium) — `database_tx.transaction()` Sets `_tx_state` Before the `try` Block

**File:** `app/shared/infrastructure/database_tx.py:51`

If `_set_in_tx(conn, True)` itself raises (e.g., lock poisoning), the `finally` block is never entered, leaving `_tx_state[id(conn)] = True` permanently — the pooled connection appears to always be inside a transaction.

**Fix:** Move `_set_in_tx(conn, True)` to be the first line *inside* the `try` block.

---

#### ERR-4 (Low) — `lock_expired_reviews` Task Has No Explicit Exception Logging

**File:** `app/tasks/scheduled.py:16`

On `cursor.execute` failure, the task retries silently with no `logger.exception` call, making it hard to trace why a task quietly retried.

**Fix:** Add explicit exception logging inside the task before re-raising.

---

### 3.4 Data Consistency Issues

#### DATA-1 (High) — TERMINATE Branch Does Not Lock the Match Row Before Writing

**File:** `app/matching/application/match_app_service.py:172`

The `TERMINATE` branch's `with self._uow.begin()` block calls `set_terminating` without first acquiring `find_by_id_for_update`. Two concurrent TERMINATE requests can both read `ACTIVE` and both call `set_terminating`, resulting in `terminated_by` and `termination_reason` being silently overwritten.

**Fix:** Inside the TERMINATE `uow` block, acquire `find_by_id_for_update` first, re-verify the status, then call `set_terminating`.

---

#### DATA-2 (Medium) — `session_service.update` Does Not Re-check Match Status After Lock

**File:** `app/teaching/application/session_service.py:99`

After acquiring the locked session row, match status is not re-verified inside the transaction. A concurrent status change from `ACTIVE` to `ended` could allow a session update on an ended match.

**Fix:** Inside the UoW block, also fetch match status and verify it remains in `_ACTIVE_SESSION_STATUSES`.

---

#### DATA-3 (Medium) — `anonymize_user` and `admin_reset_user_password` Are Not Atomic with Audit Log Inserts

**File:** `app/admin/api/router.py:308, 343`

The DML operation and `record_admin_action` are separate statements with a manual commit between them — not in a single transaction. A crash between the DML and the audit INSERT leaves a modified user with no audit trail.

**Fix:** Use `with transaction(repo.conn):` wrapping both steps.

---

### 3.5 Dead Code

| ID | File | Symbol | Reason Stale |
|---|---|---|---|
| DEAD-1 | `app/identity/api/schemas.py:56` | `TokenResponse` | Superseded by HttpOnly cookie auth; tokens no longer returned in body |
| DEAD-2 | `app/identity/domain/services.py:142` | `AuthService.logout` | Router calls `decode_refresh_token`/`invalidate_refresh_token` directly, bypassing the service |
| DEAD-3 | `app/catalog/infrastructure/postgres_tutor_repo.py:12` | `PostgresTutorRepository.search` | Superseded by `search_with_stats`; returns an incompatible shape |

---

### 3.6 API Contract Issues

#### CONTRACT-1 (Medium) — `GET /api/messages/conversations/{id}` Has No Pagination Envelope

**File:** `app/messaging/api/router.py:46`

Returns a raw `list[dict]` with no `has_more`, `next_cursor`, or `oldest_message_id`. All other list endpoints return a structured pagination envelope.

**Fix:** Return `{"items": messages, "has_more": len(messages) == limit, "oldest_message_id": ...}` and declare a `MessagesResponse` schema.

---

#### CONTRACT-2 (Low) — `list_matches` Items Are Untyped Dicts; Field Shape Diverges from `MatchDetailResponse`

**File:** `app/matching/api/router.py:71`

List items include the raw `previous_status|reason` string rather than the parsed form from `MatchDetailResponse`. The list and detail views have diverged contract surfaces with no declared schema.

**Fix:** Introduce `MatchListItemResponse` with explicit field declarations.

---

#### CONTRACT-3 (Low) — Admin Export Endpoints Have No `response_model` or `response_class` Annotation

**File:** `app/admin/api/router.py:118, 392`

Both export endpoints return `FileResponse` but declare no response schema, making the OpenAPI spec incomplete.

**Fix:** Add `response_class=FileResponse` and `responses={200: {"content": {"text/csv": {}}}}` annotations.

---

### 3.7 Cross-Cutting Observations

- **`_tx_state` dict grows without bound:** Keyed by `id(conn)`, no periodic purge. In a long-running process, entries for garbage-collected connections accumulate. Consider weakref-based tracking or connection-level attributes.
- **`_idempotency_cache` in `matching/api/router.py:28` grows without bound:** Entries accumulate over 24 hours with no LRU eviction cap. Apply the same pattern as `_blacklist_cache` in `security.py`.
- **`utils/security.py` and `utils/logger.py` are re-export shims marked "Phase 9 delete":** Clean up or document the timeline.

---

## 4. Frontend — Security, Bugs & Responsibility

> **Auditor note:** No `v-html` usage exists anywhere in the codebase (XSS surface is effectively zero). No hardcoded secrets or API keys appear in source files. JWTs are correctly in HttpOnly cookies. The CSRF double-submit pattern and token refresh deduplication are both correctly implemented.

---

### 4.1 Security Issues

#### SEC-02 (Medium) — CSP `script-src 'self'` Does Not Enforce SRI

**File:** `nginx-security-headers.conf:13`

The CSP's `script-src 'self'` allows any same-origin script without integrity checking. The `vite-plugin-sri.js` injects `integrity=` attributes on built assets, but the CSP does not require SRI (`'require-sri-for script'`). A compromised self-hosted asset would not be hash-checked.

**Fix:** Verify `index.html` contains `integrity=` on every `<script>` and `<link rel="stylesheet">` tag. For stricter enforcement, add a hash-based `script-src` in the CSP.

---

#### SEC-01 (Low) — `localStorage` Stores User Identity Data Readable by XSS

**Files:** `src/stores/auth.js:26, 50, 82, 96`; `src/stores/notifications.js:22, 70`

`user_id`, `role`, `display_name`, and notification history are persisted in `localStorage`. The existing `verified` flag correctly guards all authorization decisions against this cache. The residual risk is identity disclosure (`display_name`, `user_id`) via an XSS entry point.

**Fix:** No correctness action required given the `verified` flag. Document the residual disclosure in the security policy.

---

#### SEC-04 (Low) — SRI Plugin Does Not Inject `crossorigin="anonymous"`

**File:** `vite-plugin-sri.js:40`

Browsers may skip SRI verification on elements without `crossorigin` in some configurations.

**Fix:** Add `crossorigin="anonymous"` to every replaced `<script>` and `<link>` tag in the plugin output.

---

#### SEC-05 (Low) — nginx Does Not Assert Cookie Security Flags at Proxy Layer

**File:** `nginx.conf:55`

`proxy_cookie_flags` is not set. If the backend omits a `SameSite` flag, nginx passes the cookie through unmodified.

**Fix:** Add `proxy_cookie_flags ~ secure samesite=strict;` to the `/api/` location block (nginx ≥ 1.19.3).


2026-05-05 DONE (above)

---

### 4.2 Authentication / Authorization Bugs

#### AUTH-01 (Medium) — Route Guard Post-verify State Not Re-evaluated Clearly

**File:** `src/router/index.js:109`

After an `ensureVerified()` failure in the guard, `user.value` is set to `null` (making `auth.isLoggedIn` `false`), but subsequent guard checks still reference the pre-catch value of `auth.isLoggedIn`. The code is functionally correct due to Vue's computed reactivity, but the intent is unclear and a future refactor could introduce a real gap.

**Fix:** Add explicit comments documenting that `auth.isLoggedIn` is a computed from `user.value`, and re-read it after each `catch` block.

---

#### AUTH-02 (Medium) — `AdminDashboardView` Renders Before Role Verification Completes

**File:** `src/views/admin/AdminDashboardView.vue:527`

The admin UI (user table, seed/reset buttons, export controls) renders immediately on mount, before `ensureVerified()` resolves the server-side role check. If `verified.value` was reset (e.g., by the `storage` event listener), the template is briefly interactive before the role check fires.

**Fix:**
```js
const verifying = ref(true)
onMounted(async () => {
  try { await auth.ensureVerified() } catch {}
  if (auth.role !== 'admin') { router.push('/'); return }
  verifying.value = false
  fetchUsers()
  fetchSystemStatus()
})
```
Gate the template with `<div v-if="!verifying">`.

---

#### AUTH-03 (Low) — `useConfirm` Singleton Not Safe Against Concurrent Dialogs

**File:** `src/composables/useConfirm.js:12`

A second `confirm()` call while a dialog is open overwrites `_resolve`. The first caller's promise never settles.

**Fix:** Reject or close any pending dialog before opening a new one.

---

#### AUTH-04 (Low) — `AppNav` Prop Validator Fires on Unverified Role

**File:** `src/components/common/AppNav.vue:79`

`role === ''` during cold-start fires the validator and emits a Vue warning in the console.

**Fix:** Accept `''` as a valid transient state in the validator.

---

### 4.3 Systemic Bugs

#### BUG-01 (High) — `window.confirm` Used Instead of App Dialog in One Location

**File:** `src/views/tutor/MatchDetailView.vue:589`

`handleSessionFormCancel` calls `window.confirm` — a synchronous browser dialog — while every other destructive confirmation in the application uses `useConfirm()` (async, styled, accessible).

**Fix:**
```js
async function handleSessionFormCancel() {
  if (sessionFormRef.value?.hasDirtyData?.()) {
    if (!await confirm({ title: '確定要取消？', message: '已輸入的資料將不會儲存。' })) return
  }
  // ...
}
```

---

#### BUG-02 (Medium) — `useMatchDetail` State Not Reset When Match ID Changes Without Unmount

**File:** `src/composables/useMatchDetail.js:21`; both `MatchDetailView` files

Vue Router reuses the component instance for same-component navigation. Neither MatchDetailView watches `route.params.id` to re-fetch when navigating between matches. Old data flashes briefly before the new fetch resolves.

**Fix:**
```js
watch(() => route.params.id, (id) => { if (id) fetchMatch() })
```
Also clear `match.value`, `sessions.value`, etc. at the start of `fetchMatch`.

---

#### BUG-05 (Low) — Race Condition on Rapid Month Switching in Stats Views

**Files:** `src/views/parent/ExpenseView.vue:75`; `src/views/tutor/IncomeView.vue:73`

Two concurrent fetches triggered by rapid month changes; the slower (earlier) response can overwrite `data.value` with the wrong month's data.

**Fix:** Add a fetch sequence counter (identical pattern to `ChatView.vue`).

---

#### BUG-06 (Low) — `SearchView` Page Clamping Uses `totalPages` Before First Fetch

**File:** `src/views/parent/SearchView.vue:187`

A deep-linked `?page=5` is clamped to page 1 before any data is loaded, ignoring the user's intent.

**Fix:** Remove the `totalPages.value` upper bound from the pre-fetch `startPage` calculation; clamp after receiving `res.total`.

---

### 4.4 Responsibility Violations

#### RESP-01 (Medium) — `useMatchStore` and `useMessageStore` Are Architectural Dead Weight

**Files:** `src/stores/match.js`; `src/stores/message.js`

Both stores are imported only by `auth.js` for logout cleanup, but no view or composable reads from them. The local state in dashboard/chat views is completely independent, making the `setMatches([])`/`setConversations([])` cleanup calls no-ops.

**Fix:** Either remove the stores and their imports from `auth.js` (option A), or migrate dashboard/conversation-list local state into these stores so logout cleanup is meaningful (option B, architecturally correct).

---

#### RESP-05 (Low) — Wire-Format Parsing Logic for Termination Reason in Composable

**File:** `src/composables/useMatchDetail.js:35`

The `|`-delimited backend wire format is decoded inline in the composable. If the backend changes the delimiter, the UI silently breaks.

**Fix:** Extract to `parseTerminationReason(raw)` in `src/utils/format.js`.

---

### 4.5 Dead Code

| ID | File | Symbol |
|---|---|---|
| DEAD-02 | `src/views/messages/ConversationListView.vue:141` | `formatDate` alias and `formatDateTimeShort` import — never used in template |
| DEAD-03a | `src/api/admin.js:56` | `adminApi.getTaskStatus` — never called |
| DEAD-03b | `src/api/tutors.js:25` | `tutorsApi.getReviews` — never called (reviews fetched via `reviewsApi`) |
| DEAD-03c | `src/api/stats.js:10` | `statsApi.getStudentProgress` — never called |

---

### 4.6 Configuration

#### CONF-01 (Low) — nginx `/health` Location Missing Security Headers

**File:** `nginx.conf:70`

The `/health` location block does not include `security-headers.conf` or `Strict-Transport-Security`, allowing the health response to be iframed.

**Fix:**
```nginx
location /health {
    include /etc/nginx/snippets/security-headers.conf;
    add_header Strict-Transport-Security $hsts_header always;
    proxy_pass http://api:8000;
}
```

---

## 5. Infrastructure — Docker, Secrets & Database Schema

### 5.1 Container / Docker Compose

#### I-01 (Critical) — API Port 8000 Exposed on All Interfaces in Base Compose File

**File:** `docker-compose.yml:92`

The base compose file (designated as the production file in `SECURITY.md`) binds uvicorn on `0.0.0.0:8000`. Without the override file, the raw FastAPI backend is directly reachable from the public internet, bypassing nginx's rate-limit zone, CSP injection, XFF normalization, and dotfile blocking. `check-prod-compose.sh` only guards port 5432 and does not detect this.

**Fix:** Remove the `ports:` section for the `api` service from the base compose file entirely. Move the `127.0.0.1:8001:8000` binding into `docker-compose.override.yml`. Extend `check-prod-compose.sh` to also reject `8000` host-side bindings.

---

#### I-05 (Medium) — `docker-compose.run.yml` Sets `DEBUG=true` + `COOKIE_SECURE=false` Without Prominent Warning

**File:** `docker-compose.run.yml:9`

Applying this file against a public-facing deployment simultaneously exposes `/docs`, `/redoc`, `/openapi.json`, and sends auth cookies in cleartext. The file name (`docker-compose.run.yml`) could be confused with a "ready to run" production file.

**Fix:** Add a `# ⚠️ LOCAL DEVELOPMENT ONLY — NEVER USE IN PRODUCTION` block at the top of the file. Consider renaming to `docker-compose.local-debug.yml`.

---

### 5.2 Secrets Management

#### I-02 (High) — Admin Password Fails 4-Character-Class Validator

**File:** `secrets/admin_password.txt`

The current password (`5N90BUiaYZgGe8lGuny0fEOct6S5w4uQ`) contains only three character classes (lowercase, uppercase, digits — no symbol). `config.py:177` enforces all four classes, causing a startup `ValueError` in production mode.

**Fix:** Generate a replacement with all four classes:
```sh
python -c "import secrets, string; a=string.ascii_letters+string.digits+'!@#\$%^&*'; print(''.join(secrets.choice(a) for _ in range(32)))"
```
Also rotate the admin user's password via the admin endpoint (the old hash appears in `data/export/Users.csv`).

---

#### I-03 (Medium) — Inconsistent Password Strength Guidance Across Three Sources

| Source | Stated Requirement |
|---|---|
| `secrets/admin_password.txt.example` | "MIN_8_CHARS" |
| `docker-entrypoint.sh:71` | "12+ chars, 3+ classes" |
| `config.py` (authoritative) | ≥16 chars + all 4 classes |

**Fix:** Update the example file placeholder and the entrypoint error message to match `config.py`'s actual requirement.

---

#### I-04 (Medium) — JWT Secret and Admin Password Previously Committed to Git History (Not Purged)

The commit message at `19be7e2` acknowledges prior plaintext credential leakage. Values were rotated but the history objects were never purged with `git-filter-repo` or BFG (noted in `.pre-commit-config.yaml:9`). Anyone with repo access can recover the old values.

**Fix:** Before making the repository public, run `git-filter-repo` to purge the relevant commit objects. Verify with `git log --all -S "old_credential_pattern"`.

---

#### I-06 (Medium) — Entrypoint Blocklist Does Not Include the `.example` File Placeholder

**File:** `docker-entrypoint.sh:68`

`"REPLACE_WITH_A_STRONG_PASSWORD_MIN_8_CHARS"` (the value in the example file) is not in the `case` blocklist. An operator copying the example verbatim passes the entrypoint check but fails at `config.py` with a cryptic error.

**Fix:** Add the example file placeholder text to the `case` block.

---

#### I-10 (Medium) — `ADMIN_USERNAME=owner_change_me` in `.env.docker`

**File:** `tutor-platform-api/.env.docker:24`

The config validator rejects this in non-debug mode, but the development container sets `DEBUG=true`, bypassing the check. If used as a staging base, the admin account has a predictable username.

---

### 5.3 Database Schema

#### I-07 (Medium) — Missing CHECK Constraints on `users.role` and `matches.status`

**File:** `app/init_db.py:38, 125`

`users.role VARCHAR(10)` and `matches.status VARCHAR(15)` have no DB-level `CHECK` constraints. A direct SQL write, migration error, or malformed CSV import could introduce unrecognized values the application misinterprets.

**Fix:**
```sql
ALTER TABLE users ADD CONSTRAINT chk_users_role
    CHECK (role IN ('parent', 'tutor', 'admin'));

ALTER TABLE matches ADD CONSTRAINT chk_matches_status
    CHECK (status IN ('pending','trial','active','paused',
                      'terminating','ended','cancelled','rejected'));
```

---

#### I-14 (Low) — No CHECK on `users.email` Format or Uniqueness Index

**File:** `app/init_db.py:40`

Multiple users can register with the same email, and malformed emails are accepted at the DB level.

**Fix:**
```sql
ALTER TABLE users ADD CONSTRAINT chk_users_email_format
    CHECK (email IS NULL OR email LIKE '%@%');
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email
    ON users (email) WHERE email IS NOT NULL;
```

---

### 5.4 Scripts

#### I-08 (Medium) — `check-prod-compose.sh` Does Not Guard API Port 8000

**File:** `scripts/check-prod-compose.sh:39`

The CI script guards port 5432 only. See [I-01](#i-01-critical--api-port-8000-exposed-on-all-interfaces-in-base-compose-file) for the full impact.

**Fix:** Add a check for `8000` host-side bindings matching the existing `5432` pattern.

---

#### I-11 (Low) — `pin-base-images.sh` Uses `sed -i` Incompatible with macOS BSD sed

**File:** `scripts/pin-base-images.sh:45`

`sed -i` without a backup suffix silently fails or errors on macOS.

**Fix:** Use `sed -i.bak` (cross-platform) and add a cleanup step.

---

### 5.5 Seed Data

#### I-09 (Medium) — All Seed Users Use the Trivially Weak Password `password123`

**File:** `seed/generator.py:82`

If seed data is applied to any internet-reachable environment, all seed accounts are trivially compromised.

**Fix:** Generate per-account random passwords at seed time and print them once; or document clearly that seed data is for local development only and must never be applied to any accessible deployment.

---

### 5.6 Tests

#### I-12 (Low) — Security-Critical Paths Have No Test Coverage

**File:** `tests/` (all files)

The following paths have zero test coverage:
- `PUT /api/auth/password` (password change and reuse rejection)
- `POST /api/auth/refresh` (token consumption and JTI blacklisting)
- `POST /api/auth/logout` (token invalidation)
- Login lockout after 5 failed attempts
- CSRF double-submit enforcement
- Admin: anonymization, password reset confirm, seed trigger

**Fix:** Add `test_refresh_and_logout.py`, `test_password_policy.py`, and `test_admin_operations.py`.

---

#### I-13 (Low) — Rate-Limit and CSRF Middleware Fully Bypassed in All Tests

**File:** `tests/conftest.py:46`

`check_and_record_bucket` is globally patched to `return True` and CSRF is never exercised by `TestClient`. Middleware regressions cannot be caught.

**Fix:** Add at least one test class that verifies the rate-limited path (`check_and_record_bucket` returns `False` → 429) and the CSRF-missing path (mutating request without `X-CSRF-Token` → 403).

---

### 5.7 Data Files

#### I-15 (Low) — No `.dockerignore` — Export Files with Bcrypt Hashes Included in Docker Build Context

**File:** `tutor-platform-api/Dockerfile` (`COPY . .`)

`data/export/` (containing `Users.csv` with password hashes), `data/huey.db`, and `data/tutoring.accdb` are all included in the Docker build context because there is no `.dockerignore`.

**Fix:** Create `tutor-platform-api/.dockerignore`:
```
data/export/
data/huey.db
data/tutoring.accdb
data/backups/
logs/
__pycache__/
*.pyc
.env*
```

---

## 6. Consolidated Severity Index

| Severity | ID | File | Issue |
|----------|----|----|-------|
| **Critical** | I-01 | `docker-compose.yml:92` | API port 8000 exposed on all interfaces |
| **High** | I-02 | `secrets/admin_password.txt` | Admin password fails 4-char-class validator |
| **High** | HIGH-1 / BUG-1 | `matching/application/match_app_service.py:131` | TOCTOU: permission check on unlocked read |
| **High** | DATA-1 | `matching/application/match_app_service.py:172` | TERMINATE branch writes without row lock |
| **High** | ERR-1 | `matching/application/match_app_service.py:184` | `ValueError` propagates as unhandled 500 |
| **High** | BUG-2 | `matching/application/match_app_service.py:195` | CONFIRM_TRIAL capacity check uses stale snapshot |
| **High** | BUG-01 (FE) | `views/tutor/MatchDetailView.vue:589` | `window.confirm` inconsistent with app dialog system |
| **Medium** | MEDIUM-AUTH-2 | `admin/api/router.py:226` | Password re-verification outside transaction |
| **Medium** | MEDIUM-AUTH-3 | `matching/api/router.py:27` | In-process idempotency cache not shared across workers |
| **Medium** | MEDIUM-VAL-1 | `catalog/api/schemas.py:12` | `max_students` unbounded; 0 or -1 breaks capacity gate |
| **Medium** | MEDIUM-SENS-1 | `admin/api/router.py:257` | Pre-reset backup path logged to structured log |
| **Medium** | MEDIUM-BAC-1 | `teaching/application/session_service.py:80` | Session list accessible to ex-participants |
| **Medium** | MEDIUM-BAC-2 | `catalog/api/student_router.py:40` | No per-parent student limit |
| **Medium** | MEDIUM-RATE-1 | `catalog/api/tutor_router.py:165` | Review endpoint under default rate bucket |
| **Medium** | MEDIUM-DEF-1 | `shared/infrastructure/config.py:88` | `cookie_secure` defaults to `False` |
| **Medium** | BUG-3 | `admin/api/router.py:193` | Advisory lock released before destructive reset |
| **Medium** | BUG-4 | `teaching/application/session_service.py:96` | Session update permission on unlocked read |
| **Medium** | BUG-5 | `messaging/api/router.py:63` | Wrong REST URL for send-message endpoint |
| **Medium** | ERR-2 | `admin/api/router.py:323` | Failed audit logging obscured by raw commit |
| **Medium** | ERR-3 | `shared/infrastructure/database_tx.py:51` | `_tx_state` set before `try` block |
| **Medium** | DATA-2 | `teaching/application/session_service.py:99` | Session update: match status not re-checked after lock |
| **Medium** | DATA-3 | `admin/api/router.py:308` | Anonymize/reset not atomic with audit log insert |
| **Medium** | SRP-1 | `teaching/api/exam_router.py:26` | Business logic in router, no exam service layer |
| **Medium** | SRP-2 | `review/api/router.py:42` | Business logic in router, no review service layer |
| **Medium** | CONTRACT-1 | `messaging/api/router.py:46` | Message list has no pagination envelope or schema |
| **Medium** | SEC-02 (FE) | `nginx-security-headers.conf:13` | CSP does not enforce SRI |
| **Medium** | AUTH-01 (FE) | `router/index.js:109` | Route guard post-verify state logic unclear |
| **Medium** | AUTH-02 (FE) | `views/admin/AdminDashboardView.vue:527` | Admin UI renders before role verification |
| **Medium** | BUG-02 (FE) | `composables/useMatchDetail.js:21` | Composable state not reset on match ID change |
| **Medium** | RESP-01 (FE) | `stores/match.js`, `stores/message.js` | Dead stores; logout cleanup is a no-op |
| **Medium** | I-03 | `secrets/admin_password.txt.example` | Inconsistent password strength guidance |
| **Medium** | I-04 | Git history | Prior credentials not purged from history |
| **Medium** | I-05 | `docker-compose.run.yml:9` | `DEBUG=true` file lacks production warning |
| **Medium** | I-06 | `docker-entrypoint.sh:68` | Entrypoint blocklist incomplete |
| **Medium** | I-07 | `app/init_db.py:38, 125` | Missing CHECK constraints on `role` and `status` |
| **Medium** | I-08 | `scripts/check-prod-compose.sh:39` | CI guard doesn't check API port 8000 |
| **Medium** | I-09 | `seed/generator.py:82` | All seed users use `password123` |
| **Medium** | I-10 | `.env.docker:24` | `ADMIN_USERNAME=owner_change_me` |
| Low (×30+) | *(see sections above)* | | Input validation bounds, rate-limit buckets, dead code, minor config gaps |

---

## 7. What the Codebase Does Well

Despite the findings above, this codebase demonstrates strong security and engineering practices across several critical areas:

**Security:**
- No SQL injection anywhere — all queries use psycopg2 `%s` parameterisation; dynamic identifiers use `psql.Identifier`; LIKE inputs use `escape_like()`.
- JWT implementation is hardened: `alg=none` is explicitly rejected before decode, token type is validated, HMAC key enforced ≥ 32 chars at startup.
- Tokens are delivered exclusively via HttpOnly, SameSite=Lax cookies — never in response bodies.
- CSRF double-submit cookie pattern uses `secrets.compare_digest` for constant-time comparison.
- Rate limiting is PostgreSQL-backed, multi-worker-safe, advisory-lock-serialised per bucket — covers both per-username and per-IP login paths.
- bcrypt with timing-normalisation dummy hashing on unknown usernames prevents username enumeration via timing.
- Password reuse prevention across last 5 hashes, stored atomically.
- Column allowlist (`validate_columns()`) consistently applied everywhere dynamic UPDATE is built.
- Sensitive data suppression: raw input and context are scrubbed from validation error responses.
- `ENABLE_DOCS` and `COOKIE_SECURE` validated at startup and blocked in production configurations.
- Container hardening: `no-new-privileges`, `cap_drop: ALL`, non-root UIDs, SHA-256 image pins — all present.

**Frontend:**
- No `v-html` usage anywhere — XSS surface is effectively zero.
- No hardcoded secrets or API keys in source files.
- The `verified` flag pattern correctly treats `localStorage` role as an untrusted cache, with server-round-trip verification guarding all authorization decisions.
- Token refresh deduplication using a single in-flight Promise is correct and race-condition-free.
- The `fetchId`/sequence-counter pattern in `useMatchDetail` and `ChatView` correctly guards against stale response overwrites.

**Architecture:**
- The state machine for match transitions is clearly modelled with explicit allowed-transition tables.
- The Unit of Work pattern is consistently applied across the matching and teaching domains.
- The `transaction()` context manager correctly handles nested transactions (no-op on inner entry).
- The `SECURITY.md` document is thorough and accurately describes the implemented controls.
