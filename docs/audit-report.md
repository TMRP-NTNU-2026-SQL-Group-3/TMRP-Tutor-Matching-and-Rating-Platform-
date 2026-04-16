# TMRP Full-Stack Audit Report

**Date:** 2026-04-16
**Scope:** Backend API, Frontend UI, API-Frontend Integration, Security, Database & Data Layer

---

## Table of Contents

- [Executive Summary](#executive-summary)
- [1. Security Findings](#1-security-findings)
- [2. Backend API Findings](#2-backend-api-findings)
- [3. Frontend Findings](#3-frontend-findings)
- [4. Database & Data Layer Findings](#4-database--data-layer-findings)
- [5. API-Frontend Integration](#5-api-frontend-integration)
- [6. Remediation Priority](#6-remediation-priority)

---

## Executive Summary

| Category              | Critical | High | Medium | Low | Total |
|-----------------------|----------|------|--------|-----|-------|
| Security              | 2        | 4    | 5      | 7   | 18    |
| Backend API           | 0        | 2    | 4      | 5   | 11    |
| Frontend              | 0        | 3    | 6      | 8   | 17    |
| Database & Data Layer | 2        | 1    | 4      | 6   | 13    |
| Integration           | 0        | 0    | 0      | 0   | 0     |
| **Total**             | **4**    | **10** | **19** | **26** | **59** |

The API-to-frontend wiring is fully compatible (all 51 frontend calls match their backend endpoints). The most urgent items are secrets in version control, localStorage token storage, and missing database indexes that cause full table scans.

---

## 1. Security Findings

### CRITICAL

#### SEC-C01 — Hardcoded Secrets Committed to Repository
- **File:** `tutor-platform-api/.env`
- **Detail:** Production `JWT_SECRET_KEY` and `ADMIN_PASSWORD` are present in the committed `.env` file. Any party with repository access can assume admin identity.
- **Fix:** Remove `.env` from git history (`git filter-branch` or `bfg-repo-cleaner`), rotate all secrets, add `.env` to `.gitignore`.

#### SEC-C02 — JWT Tokens Stored in localStorage (XSS Risk)
- **Files:** `tutor-platform-web/src/stores/auth.js:12,36,40`
- **Detail:** Access and refresh tokens are persisted to `localStorage`, which is readable by any script running on the page. An XSS vulnerability would allow full account takeover. The codebase acknowledges this with comment `M-01: pending migration to HttpOnly cookies`.
- **Fix:** Migrate to `HttpOnly`, `Secure`, `SameSite` cookies. Add CSRF protection when cookies are enabled.

### HIGH

#### SEC-H01 — SQL String Interpolation in Tutor Repository
- **Files:** `tutor-platform-api/app/catalog/infrastructure/postgres_tutor_repo.py:235,242`
- **Detail:** `update_visibility()` and `update_profile()` use f-string interpolation for column names (`f"{col} = %s"`). A `validate_columns()` whitelist mitigates direct injection, but the pattern is inconsistent with the rest of the codebase which uses `psycopg2.sql.Identifier()`.
- **Fix:** Replace f-string column interpolation with `psycopg2.sql.Identifier()`.

#### SEC-H02 — SQL String Interpolation in Base Repository
- **File:** `tutor-platform-api/app/shared/infrastructure/base_repository.py:35`
- **Detail:** `safe_update()` uses `f"UPDATE {table} SET {set_clause} WHERE {id_col} = %s"`. Table and `id_col` names come from trusted caller code, but are not parameterized.
- **Fix:** Use `psycopg2.sql.Identifier()` for table and column references.

#### SEC-H03 — Logout Race Condition with In-Flight Requests
- **Files:** `tutor-platform-web/src/api/index.js:26,31-34,56`
- **Detail:** Setting the `loggingOut` fence does not cancel in-flight requests. A 401 response arriving after logout could trigger a token refresh that resurrects an old session.
- **Fix:** Use an `AbortController` to cancel all pending requests when `logout()` is called.

#### SEC-H04 — Database Secrets Exposed in Container Environment
- **File:** `docker-compose.yml:12-14,41`
- **Detail:** PostgreSQL credentials are interpolated as environment variables, visible to any process inspecting container state.
- **Fix:** Use Docker secrets or IAM-based authentication for production deployments.

### MEDIUM

#### SEC-M01 — Access Tokens Not Revoked on Logout
- **File:** `tutor-platform-api/app/main.py:99-107`
- **Detail:** Only refresh-token JTIs are blacklisted on logout. A stolen access token remains valid for up to 5 minutes (capped at 15 by lifespan check).
- **Mitigation:** Current 5-minute TTL is acceptable for classroom scope. For production, implement access-token JTI blacklist.

#### SEC-M02 — CSP Allows `unsafe-inline` for Styles
- **File:** `tutor-platform-web/nginx.conf:37-38`
- **Detail:** `style-src 'self' 'unsafe-inline'` is required by Tailwind's inline styles. This enables UI redressing if an attacker can inject arbitrary HTML/CSS.
- **Fix:** Migrate to nonce-based CSP for styles (long-term, per M-05 comment).

#### SEC-M03 — Rate Limiting Fails Open on Non-Critical Paths
- **File:** `tutor-platform-api/app/middleware/rate_limit.py:30-42`
- **Detail:** Only auth/admin paths are fail-closed when the rate-limit DB is unreachable. Other endpoints (tutor search, review posting) allow unlimited traffic during outages.
- **Fix:** Add in-memory fallback rate limiting or Redis-based rate limiting.

#### SEC-M04 — Admin Reset Token Not Bound to JTI
- **File:** `tutor-platform-api/app/admin/api/router.py:124`
- **Detail:** Reset confirmation tokens are verified by user_id but not blacklisted after use. A token could theoretically be replayed within its TTL.
- **Fix:** Blacklist reset-token JTI on use, similar to refresh tokens.

#### SEC-M05 — CORS Transition Risk
- **File:** `tutor-platform-api/app/main.py:181-189`
- **Detail:** When the planned HttpOnly cookie migration (M-01) occurs, CORS must switch to `allow_credentials=True` and CSRF protection must be added simultaneously. If either step is missed, the application becomes vulnerable.
- **Fix:** Create a migration checklist issue with all required steps.

### LOW

| ID | File | Summary |
|----|------|---------|
| SEC-L01 | `shared/infrastructure/config.py:8-9` | Default pool min=2 may starve multi-worker deployments |
| SEC-L02 | `shared/api/health_router.py:22-44` | Health endpoint leaks admin vs. non-admin response shape |
| SEC-L03 | `middleware/rate_limit.py:117-138` | Rate-limit cleanup is event-driven; records accumulate during zero-traffic periods |
| SEC-L04 | `main.py:73-85` | Request IDs in 500 responses are useful but could be used for correlation |
| SEC-L05 | `catalog/infrastructure/postgres_tutor_repo.py:33,76` | Manual LIKE wildcard escaping is correct but fragile |
| SEC-L06 | `tutor-platform-web/scripts/check-no-v-html.mjs` | v-html check only runs at build time; no ESLint rule for `innerHTML` |
| SEC-L07 | `shared/infrastructure/config.py:16` | HS256 algorithm is hardcoded; symmetric key limits federated auth |

---

## 2. Backend API Findings

### HIGH

#### BE-H01 — Race Condition in Conversation Creation
- **File:** `messaging/infrastructure/postgres_message_repo.py:51-64`
- **Detail:** `get_or_create_conversation` catches generic `Exception` on INSERT conflict fallback. If the INSERT fails for reasons other than uniqueness (e.g., FK violation from a deleted user), the fallback SELECT could return stale data.
- **Fix:** Catch only `psycopg2.errors.UniqueViolation` instead of bare `Exception`.

#### BE-H02 — Incomplete Match State Machine (disagree_terminate)
- **File:** `matching/domain/state_machine.py:54,73`
- **Detail:** `DISAGREE_TERMINATE` returns `None` instead of re-entering `TERMINATING` state. No validation that the other party (not the initiator) must submit the disagreement.
- **Fix:** Add explicit state handling that returns `TERMINATING` and validates the actor is the non-initiating party.

### MEDIUM

#### BE-M01 — Schema Mismatch on Match start_date Type
- **File:** `matching/api/schemas.py:46,56`
- **Detail:** `start_date` is declared as `datetime | None` in the response schema but `MatchStatusUpdate` defines it as `date | None`. The database stores `TIMESTAMPTZ`. The inconsistency could cause serialization surprises.
- **Fix:** Standardize to `date` or `datetime` across response schema, update schema, and database.

#### BE-M02 — Session Edit Log String Comparison Defect
- **File:** `teaching/application/session_service.py:92-97`
- **Detail:** The `_as_str()` comparison for change detection could miss changes when numerically different values stringify identically (e.g., `1.0` vs `1`).
- **Fix:** Implement type-aware comparison or normalize values before comparison.

#### BE-M03 — Missing Error Handling in Admin Reset Confirm
- **File:** `admin/api/router.py:123`
- **Detail:** `decode_reset_confirmation_token` is called without catching JWT decode errors, which could surface raw library exceptions to the client.
- **Fix:** Wrap in try-except and return a structured 400 error.

#### BE-M04 — Termination Reason Parsing Fragile
- **File:** `matching/domain/entities.py:35-46`
- **Detail:** `parsed_termination_reason` assumes a `|` separator and falls back to `"active"` by default, which could hide the actual reason if the stored format doesn't match expectations.
- **Fix:** Add explicit format validation and a more informative fallback.

### LOW

| ID | File | Summary |
|----|------|---------|
| BE-L01 | `catalog/infrastructure/postgres_tutor_repo.py:63-66` | Silent default for unknown `sort_by` value instead of raising an error |
| BE-L02 | `review/api/router.py:74-94` | Review update: concurrent changes between `get_for_update` and time check could allow stale edits |
| BE-L03 | `teaching/api/exam_router.py:39` | Rate-limit bucket key format doesn't escape IDs (collision risk with special chars) |
| BE-L04 | `admin/api/router.py:5` | `Body` imported but inconsistently used compared to other routers |
| BE-L05 | `init_db.py:232` | `audit_log.actor_user_id` uses `ON DELETE SET NULL`, leaving anonymous audit records for deleted admins |

---

## 3. Frontend Findings

### HIGH

#### FE-H01 — Missing Session Edit History UI
- **Files:** `src/api/sessions.js:13-15` (API exists), views do not use it
- **Detail:** The backend provides `GET /api/sessions/{id}/edit-logs` and the frontend API wrapper `getEditLogs()` exists, but no view or component renders the edit history. Users cannot see the audit trail of session changes.
- **Fix:** Add an edit-history panel or modal in the tutor MatchDetailView session section.

#### FE-H02 — Missing Tutor Profile Visibility Toggle
- **Files:** `src/api/tutors.js:22-23` (API exists), no UI
- **Detail:** `updateVisibility()` exists in the API layer, but there is no UI component for tutors to toggle which profile fields are publicly visible (university, major, rates, etc.). This is a documented core feature.
- **Fix:** Add a visibility settings section in `tutor/ProfileView.vue`.

#### FE-H03 — Admin Password Reset Uses `window.prompt()`
- **File:** `src/views/admin/AdminDashboardView.vue:281`
- **Detail:** The admin password-reset flow collects the new password via `window.prompt()`, which displays the password in plaintext on screen.
- **Fix:** Replace with a dedicated modal containing a masked `<input type="password">`.

### MEDIUM

#### FE-M01 — Missing Exam Edit/Delete Functionality
- **Files:** `src/api/exams.js` (no delete endpoint), `src/views/tutor/MatchDetailView.vue`
- **Detail:** Tutors can create exam records but cannot edit or delete them. Mistakes in exam scores are permanent.
- **Fix:** Add edit/delete buttons in the exam table, wire to `PUT /api/exams/{examId}`.

#### FE-M02 — Missing Session Edit/Delete UI
- **File:** `src/components/session/SessionTimeline.vue`
- **Detail:** SessionTimeline is read-only. There is no way to correct or delete a session record after creation, despite the backend supporting `PUT /api/sessions/{sessionId}`.
- **Fix:** Add edit/delete actions to SessionTimeline items.

#### FE-M03 — Exam Score Input Missing Upper Bound
- **File:** `src/views/tutor/MatchDetailView.vue:186`
- **Detail:** The score `<input type="number">` has no `max` attribute. Users can enter values like 500 or negative numbers.
- **Fix:** Add `min="0" max="100"` (or appropriate ceiling) plus client-side validation.

#### FE-M04 — Message Search Only Filters Locally on Truncated Preview
- **File:** `src/views/messages/ConversationListView.vue:63-70`
- **Detail:** Search filters conversations on a 50-character preview string, so users cannot find conversations by message content.
- **Fix:** Add server-side message search or at minimum expand the local search to full last-message content.

#### FE-M05 — Admin Table Counts Not Drillable
- **File:** `src/views/admin/AdminDashboardView.vue:16-23`
- **Detail:** System status shows table row counts, but admins cannot click through to view the actual records.
- **Fix:** Make counts clickable, linking to a data-browser view or at minimum to CSV export.

#### FE-M06 — Session Timezone Not Displayed
- **Files:** `src/views/tutor/MatchDetailView.vue`, `src/components/session/SessionTimeline.vue`
- **Detail:** Session times are displayed in the browser's local timezone with no indicator. If tutor and parent are in different timezones, they see different times for the same record.
- **Fix:** Display the timezone abbreviation or store/display in UTC with conversion.

### LOW

| ID | File | Summary |
|----|------|---------|
| FE-L01 | `src/components/common/AppNav.vue:70-76` | Role prop has no validator; invalid role produces empty nav silently |
| FE-L02 | `src/components/review/ReviewList.vue:29-32` | `typeLabel()` only handles 3 known types; unknown types render as raw strings |
| FE-L03 | `src/components/common/EmptyState.vue:4` | Default icon is `'---'` which is not meaningful |
| FE-L04 | `src/views/parent/MatchDetailView.vue:277-278` | Comment says "removed terminating status" but code still checks for it at lines 47, 92-94 |
| FE-L05 | `src/views/parent/MatchDetailView.vue:294-295` | `review_type` field in reviewForm is set but then hardcoded on submit — dead assignment |
| FE-L06 | `src/views/messages/ChatView.vue` | Polling continues when browser tab is not visible / device is offline |
| FE-L07 | `src/views/tutor/ProfileView.vue:259-269` | If `updateSubjects` fails after `updateProfile` succeeds, partial save occurs (message shown, but data state is split) |
| FE-L08 | Multiple views | Inconsistent error message casing (mix of Chinese/English, formal/informal) |

---

## 4. Database & Data Layer Findings

### CRITICAL

#### DB-C01 — Missing Indexes on conversations.user_a_id / user_b_id
- **File:** `init_db.py` (index section, after line 260)
- **Query:** `postgres_message_repo.py:28` — `WHERE c.user_a_id = %s OR c.user_b_id = %s`
- **Detail:** The `idx_conversations_pair` unique index requires both columns (AND), so this OR query forces a full table scan on every conversation-list fetch.
- **Fix:**
  ```sql
  CREATE INDEX IF NOT EXISTS idx_conversations_user_a ON conversations (user_a_id);
  CREATE INDEX IF NOT EXISTS idx_conversations_user_b ON conversations (user_b_id);
  ```

#### DB-C02 — Missing Foreign Key Supporting Indexes
- **File:** `init_db.py:93-94`
- **Detail:** The `conversations` table has `ON DELETE CASCADE` foreign keys on `user_a_id` and `user_b_id` but no supporting indexes. PostgreSQL must sequentially scan `conversations` whenever a user is deleted.
- **Fix:** Same indexes as DB-C01.

### HIGH

#### DB-H01 — Race Condition in Match Capacity Checks
- **Files:** `matching/infrastructure/postgres_match_repo.py`, `catalog/infrastructure/catalog_query_adapter.py:19-27`
- **Detail:** `lock_tutor_for_update()` uses `SELECT ... FOR UPDATE`, but two concurrent `create_match` calls could both pass the `active < max_students` check if the lock scope doesn't cover the full operation.
- **Fix:** Verify that the transaction in the matching service holds the `FOR UPDATE` lock from the capacity check through the `INSERT INTO matches`.

### MEDIUM

#### DB-M01 — avg_rating NULL Handling Biases Ratings Downward
- **File:** `init_db.py:313-320` (v_tutor_ratings materialized view)
- **Detail:** `COALESCE(..., 0)` treats missing rating dimensions as 0 in the average calculation. A tutor with only 2 of 4 dimensions rated has their average pulled toward 0.
- **Fix:** Sum only non-NULL dimensions in both numerator and denominator.

#### DB-M02 — Missing Composite Index for Parent-Scoped Match Queries
- **File:** `init_db.py`
- **Detail:** `idx_matches_parent` exists but a composite `(parent_user_id, status)` index would serve the common "list my active matches" query pattern more efficiently.
- **Fix:**
  ```sql
  CREATE INDEX IF NOT EXISTS idx_matches_parent_status ON matches (parent_user_id, status);
  ```

#### DB-M03 — Subject Category Has No CHECK Constraint
- **File:** `init_db.py:432-445`
- **Detail:** Categories are seeded as `math`, `science`, `lang`, `other` but stored as unconstrained `VARCHAR`. A misconfigured insert could store invalid values.
- **Fix:**
  ```sql
  ALTER TABLE subjects ADD CONSTRAINT chk_subject_category
      CHECK (category IN ('math', 'science', 'lang', 'other'));
  ```

#### DB-M04 — Stats Task Year Upper Bound Hardcoded to 2100
- **File:** `tasks/stats_tasks.py:14-30`
- **Detail:** `_parse_month()` validates year range as `2000-2100`. While far in the future, a dynamic cap like `current_year + 10` would be more robust.

### LOW

| ID | File | Summary |
|----|------|---------|
| DB-L01 | `init_db.py:28,31,32,69` | Several VARCHAR lengths are tight (username 50, display_name 50, phone 20, category 20) |
| DB-L02 | `shared/infrastructure/base_repository.py:20-24` | `close()` silently catches all exceptions on cursor cleanup |
| DB-L03 | `shared/infrastructure/database_tx.py:23-40` | Nested transaction handling assumes connections support `_in_tx` attribute assignment |
| DB-L04 | `init_db.py:230-240` | `audit_log.resource_id` is a soft reference (no FK) — intentional but undocumented in consuming code |
| DB-L05 | No dedicated file | Missing `postgres_conversation_repo.py` — all conversation ops live in `PostgresMessageRepository` |
| DB-L06 | `init_db.py:250-277` | No index on `messages.conversation_id` for large conversation histories (may already be covered by FK index) |

---

## 5. API-Frontend Integration

**Status: Fully Compatible**

All 51 frontend API calls were audited against their 50 backend endpoints. No mismatches were found in:
- HTTP methods and URL paths
- Request body schemas and required fields
- Response envelope structure (`{ success, data, message }`)
- Query parameter names and types
- Path parameter naming
- Blob response handling (CSV/ZIP exports)
- Auth token refresh flow and error handling
- Multipart upload Content-Type handling

One expected gap: the `/health` endpoint is not called by the frontend (used by Docker healthcheck / monitoring only).

---

## 6. Remediation Priority

### Immediate (This Week)

| # | ID | Action |
|---|----|--------|
| 1 | SEC-C01 | Remove `.env` from git history, rotate all secrets, ensure `.gitignore` coverage |
| 2 | DB-C01 | Add missing conversation user indexes (fixes full table scans) |
| 3 | SEC-H01/H02 | Replace f-string SQL interpolation with `psycopg2.sql.Identifier()` |
| 4 | FE-H03 | Replace `window.prompt()` with password input modal in admin reset |

### Short-Term (This Sprint)

| # | ID | Action |
|---|----|--------|
| 5 | SEC-C02 | Begin HttpOnly cookie migration (design + prototype) |
| 6 | FE-H01 | Add session edit history UI |
| 7 | FE-H02 | Add tutor profile visibility toggle UI |
| 8 | BE-H01 | Catch `UniqueViolation` specifically in conversation creation |
| 9 | BE-H02 | Fix disagree_terminate state machine transition |
| 10 | DB-H01 | Verify match capacity lock scope covers full transaction |
| 11 | FE-M01/M02 | Add exam and session edit/delete UI |

### Medium-Term (Next Sprint)

| # | ID | Action |
|---|----|--------|
| 12 | SEC-H03 | Add AbortController to cancel in-flight requests on logout |
| 13 | DB-M01 | Fix avg_rating NULL handling in materialized view |
| 14 | DB-M02 | Add composite index `(parent_user_id, status)` |
| 15 | BE-M01 | Standardize `start_date` type across schema |
| 16 | FE-M03 | Add score input validation bounds |
| 17 | FE-M04 | Improve message search (server-side or expanded local) |
| 18 | SEC-M02 | Plan nonce-based CSP migration |

### Low Priority (Backlog)

All items marked **LOW** across all categories. These are code quality improvements, minor UX polish, and documentation tasks that do not affect correctness or security.

---

*Generated by automated multi-agent audit. All file paths and line numbers reference the codebase state as of 2026-04-16.*
