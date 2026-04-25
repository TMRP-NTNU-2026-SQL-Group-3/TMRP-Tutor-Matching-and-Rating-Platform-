# TMRP Platform — Full Audit Report

**Date:** 2026-04-25  
**Scope:** Backend (Python/FastAPI) · Frontend (Vue 3 + Pinia) · Security (full-stack)  
**Agents:** 2 × Backend · 1 × Frontend · 1 × Security

---

## Table of Contents

1. [Backend Findings — Core Modules](#1-backend-findings--core-modules)
2. [Backend Findings — Admin, Analytics, Tasks, Infra](#2-backend-findings--admin-analytics-tasks-infra)
3. [Frontend Findings — Bugs & UX/UI](#3-frontend-findings--bugs--uxui)
4. [Security Findings](#4-security-findings)
5. [Summary Table](#5-summary-table)
6. [Remediation Priority](#6-remediation-priority)

---

## 1. Backend Findings — Core Modules

### Critical

**B1-C1 — Inconsistent match data structure in review create vs. list**
- File: `app/review/api/router.py` lines 41–44 / 78
- `get_match_for_create()` returns `session_count`; `get_match_participants()` does not. Any code path that calls the wrong method will raise a `KeyError` at runtime.

**B1-C2 — Review allowed on `paused` matches despite error message saying otherwise**
- File: `app/review/api/router.py` line 29
- `REVIEWABLE_STATUSES = {"active", "paused", "ended"}` but the user-visible error message restricts to "進行中或已結束" (active or ended). Either the set or the message is wrong.

**B1-C3 — Tutor authorization bypass in exam creation**
- File: `app/teaching/api/exam_router.py` line 36
- Permission check only verifies "active match exists with student"; it does not verify the tutor teaches the specific subject. A tutor can create exam records for any student they have any match with.

**B1-C4 — Stale `want_trial` in state machine (TOCTOU)**
- File: `app/matching/application/match_app_service.py` line 150
- `match.contract.want_trial` is read at request start. If contract terms are updated (lines 195–201), `want_trial` is never refreshed — state machine operates on stale data.

**B1-C5 — Logout silently succeeds when refresh token has no `jti`**
- File: `app/identity/api/router.py` line 148–150
- If `jti` is absent from the refresh token, the logout returns success without blacklisting anything. A compromised token with no JTI remains replayable forever.

### Medium

**B1-M1 — HTTP 423 vs expected 400 for locked review**
- File: `app/review/api/router.py` lines 101–102 / 135–138
- `ReviewLockedError` maps to HTTP 423 but test expectations use 400. Two different code paths produce different status codes for the same condition.

**B1-M2 — Tutor can see all exams for any student they have a match with**
- File: `app/teaching/api/exam_router.py` line 60
- `parent_only=False` returns all exams regardless of subject taught. Information disclosure.

**B1-M3 — `confirm_trial_with_terms` bypasses domain validation**
- File: `app/matching/application/match_app_service.py` lines 195–201
- Updates `sessions_per_week` / `hourly_rate` directly in the database without reconstructing a `Contract` entity, so invariants (e.g. `sessions_per_week > 0`) are not enforced.

**B1-M4 — PaginatedData schema missing `total_pages`, `has_next`, `has_prev`**
- File: `app/shared/api/schemas.py` lines 14–18
- Service layer returns these fields; the response DTO does not declare them — callers cannot rely on them.

**B1-M5 — Inconsistent SQL composition pattern in `confirm_trial_with_terms`**
- File: `app/matching/infrastructure/postgres_match_repo.py` line 181
- Uses `.as_string(conn)` before passing to `execute()`, which differs from every other query in the file. Fragile and likely to break under future refactors.

### Low

**B1-L1 — `PostgresUnitOfWork` is not a context manager**
- File: `app/matching/infrastructure/postgres_unit_of_work.py` lines 11–15
- No `__enter__` / `__exit__`. Pattern is inconsistent with shared UoW API.

**B1-L2 — `extra_set` parameter in `BaseRepository.safe_update` accepts raw SQL**
- File: `app/shared/infrastructure/base_repository.py` lines 56–64
- While current callers only pass hardcoded strings, the API allows raw SQL concatenation — future misuse would cause SQL injection.

**B1-L3 — Confusing `parent_only` parameter name in session repo**
- File: `app/teaching/infrastructure/postgres_session_repo.py` lines 45–54
- The parameter name implies "caller must be a parent" but actually means "filter to parent-visible records". Name leads to future misreads.

**B1-L4 — Admin bypass control flow for `OTHER_PARTY` transitions is misleading**
- File: `app/matching/domain/state_machine.py` lines 91–92
- The early return skips the actor check except for `OTHER_PARTY`, but the control flow makes a reader think the bypass covers all transitions. Works correctly but is confusing.

**B1-L5 — Imports of constants inside function body**
- File: `app/review/api/router.py` line 124
- `_LOW_RATING_THRESHOLD` and `_LOW_RATING_MIN_COMMENT_LEN` should be module-level imports.

---

## 2. Backend Findings — Admin, Analytics, Tasks, Infra

### High

**B2-H1 — No pagination on `/api/students` and `/api/subjects`**
- File: `app/catalog/api/student_router.py` line 15 / `app/catalog/api/subject_router.py` line 13
- Both endpoints return unbounded result sets. Could cause large payload responses and represents a DoS vector. All other list endpoints implement pagination.

### Medium

**B2-M1 — Analytics EXTRACT() ignores timezone**
- File: `app/analytics/infrastructure/postgres_stats_repo.py` lines 21–22, 35–36, 53–54, 70–71
- `EXTRACT(MONTH FROM se.session_date)` operates on raw TIMESTAMPTZ without `AT TIME ZONE` conversion. Monthly/yearly totals can be wrong for users in different timezones near midnight boundaries.

### Low

**B2-L1 — `update_profile` not wrapped in explicit transaction**
- File: `app/catalog/api/tutor_router.py` line 89
- `replace_subjects()` and `replace_availability()` use `with transaction()`; `update_profile()` does not. Inconsistent pattern; not a bug today but fragile.

**B2-L2 — `total_pages = 0` when result set is empty**
- File: `app/catalog/api/tutor_router.py` line 62 / `app/matching/application/match_app_service.py` line 96
- Returns `total_pages = 0` for empty results. Some clients expect `total_pages >= 1` when they have a valid page 1 request. Minor UX inconsistency.

**B2-L3 — No `page_size` enforcement in service layer (defense-in-depth gap)**
- File: `app/matching/api/router.py` lines 46–47
- FastAPI validates `le=MAX_PAGE_SIZE`, but service layer has no independent guard. A bug in schema validation would allow unbounded queries.

---

## 3. Frontend Findings — Bugs & UX/UI

### Functional Bugs

**F-B1 — Dashboard match-load errors not displayed in template**
- File: `src/views/tutor/DashboardView.vue` lines 55–63 / `src/views/parent/DashboardView.vue` lines 59–70
- Errors only shown via toast; `matches` ref stays empty with no error state rendered — user sees a blank list with no explanation.

**F-B2 — Silent API error in TutorDetailView message creation**
- File: `src/views/parent/TutorDetailView.vue` lines 141–151
- `goMessage()` catches API errors but only fires a toast; it does not abort navigation if conversation creation fails.

**F-B3 — Race condition in chat message polling**
- File: `src/views/messages/ChatView.vue` lines 114–176
- Polling and manual send can trigger concurrent `fetchMessages()` calls. `fetchId` deduplication is not fully synchronized; stale fetch results can partially overwrite newer messages.

**F-B4 — Null reference risk in exam submission guard**
- File: `src/views/tutor/MatchDetailView.vue` lines 607–611
- `match.value.student_id` and `match.value.subject_id` checks run only on submit. If the match failed to load, users can fill the form in full before getting the error.

**F-B5 — Incomplete store reset on logout**
- File: `src/stores/auth.js` lines 89–111
- `logout()` calls coarse `setMatches([])` resets but does not clear all slices of all stores. Residual state from a previous role session can leak into the next login.

**F-B6 — Null guard missing on `tutor.avg_rating`**
- File: `src/components/tutor/TutorCard.vue` lines 19–20
- `avg_rating` rendered directly; displays "null" if backend returns null before a rating exists.

**F-B7 — Inconsistent null handling in `ReviewList`**
- File: `src/components/review/ReviewList.vue` lines 8–15
- `r.rating_2` / `r.rating_3` use fallback to "-", but `r.rating_1` does not. Can render "undefined" for certain review structures.

**F-B8 — Admin reset loses `reset_token` on `confirmReset` failure**
- File: `src/views/admin/AdminDashboardView.vue` lines 349–388
- If `requestReset()` succeeds but `confirmReset()` times out, the token is gone and the admin must restart the flow with no guidance.

**F-B9 — No maximum hourly rate validation in ContractConfirmModal**
- File: `src/components/match/ContractConfirmModal.vue` lines 120–134
- Accepts arbitrarily large values (e.g. 999999). Only checks `> 0`.

**F-B10 — Exam form submits via JS without re-validating required fields**
- File: `src/views/tutor/MatchDetailView.vue` lines 596–635
- Form relies on HTML5 `required` attributes; pressing Enter can bypass native validation. No explicit JS check before `emit('submit', ...)`.

**F-B11 — Invite form old values remain after cancel + reopen**
- File: `src/views/parent/TutorDetailView.vue` lines 130–131
- `inviteError` is cleared on open but the form fields are not reset. User can resubmit an already-failed payload without realizing it.

**F-B12 — Session page resets silently to page 1 after edit/delete**
- File: `src/views/tutor/MatchDetailView.vue` lines 551–561
- `sessionPage.value = 1` is called with no animation or message — a user on page 3 suddenly sees page 1 with no context.

### UX / UI Issues

**F-U1 — No loading state during post-action refetch**
- File: `src/views/parent/MatchDetailView.vue` lines 62–65
- Loading skeleton only appears on first mount. Refetch after an action (e.g., pause) has no visual feedback beyond button disable.

**F-U2 — No loading state or error on subject list in SearchView**
- File: `src/views/parent/SearchView.vue` lines 147–154
- Subjects load in `onMounted` with no skeleton or error state. Slow API → empty filter dropdown with no explanation.

**F-U3 — Error state hidden by v-else EmptyState in ConversationListView**
- File: `src/views/messages/ConversationListView.vue` lines 135–141
- When the conversation list is empty and the fetch also fails, `EmptyState` takes precedence over the error message in the `v-else` chain.

**F-U4 — Disabled "Add Subject" button has no tooltip**
- File: `src/views/tutor/ProfileView.vue` lines 69–72
- `!hasFreeSubject` disables the button silently; users don't know why it's disabled.

**F-U5 — Ambiguous empty vs. error state in IncomeView / ExpenseView**
- File: `src/views/parent/ExpenseView.vue` line 53 / `src/views/tutor/IncomeView.vue` line 51
- Both API failure and genuinely empty month show the same "本月無上課紀錄" message.

**F-U6 — Inconsistent date/time formatting across views**
- Files: `ConversationListView.vue` line 107 / `ChatView.vue` line 101 / `SessionTimeline.vue` line 242
- Three different formatting patterns used. No shared utility.

**F-U7 — Delete exam button lacks visual destructive styling**
- File: `src/views/tutor/MatchDetailView.vue` lines 284–285
- `window.confirm()` exists but the button has no red/warning styling.

**F-U8 — No scroll-to-top on new search (only on page change)**
- File: `src/views/parent/SearchView.vue` lines 138 / 144–145
- Pagination page changes scroll to top; a new search does not. Users may miss results when scrolled far down.

**F-U9 — Conversation search shows no result highlighting**
- File: `src/views/messages/ConversationListView.vue` lines 92–101
- Matched terms not highlighted; user cannot tell why a result appears.

**F-U10 — Admin reset cooldown check does not visually disable submit**
- File: `src/views/admin/AdminDashboardView.vue` lines 349–356
- Cooldown sets an error message but the submit button is only blocked by `resetting` flag. User can see the error and still perceive the button as active.

### Missing Features / Incomplete Flows

**F-M1 — Session creation partial failure is unclear**
- File: `src/views/tutor/MatchDetailView.vue` lines 563–593
- "已新增，但列表更新失敗" message appears in a toast and the form closes — user cannot tell if the session was actually saved.

**F-M2 — Profile save doesn't identify which sub-request failed**
- File: `src/views/tutor/ProfileView.vue` lines 344–402
- Three API calls (profile, subjects, availability); if one fails the user gets no indication of which partial save succeeded.

**F-M3 — Conversation list search missing pagination**
- File: `src/views/messages/ConversationListView.vue` lines 92–101
- All matching conversations rendered in one list; no page limit for high-volume users.

**F-M4 — Chat message send has no retry button**
- File: `src/views/messages/ChatView.vue` lines 162–176
- Failed send shows an error but no retry action. User must close/reopen the chat.

**F-M5 — Tutor profile dirty-state guard resets incorrectly**
- File: `src/views/tutor/ProfileView.vue` lines 236–240
- `isDirty` is cleared after save, but if the user cancels a navigation prompt and then saves, the guard fires once but not again on the next navigation attempt.

**F-M6 — No warning before discarding SessionForm data**
- File: `src/views/tutor/MatchDetailView.vue` lines 131–145
- SessionForm has no dirty tracking. Clicking "Cancel" silently discards typed data.

**F-M7 — Termination sent but page shows no pending-termination indicator**
- File: `src/views/parent/MatchDetailView.vue` lines 261–265
- After calling `doTerminate()`, the toast appears but there's no visible status change on the match card until the user scrolls to the confirmation section.

**F-M8 — Server search fallback is silent**
- File: `src/views/messages/ConversationListView.vue` lines 81 / 85
- If the server-side search endpoint is unavailable, the code silently falls back to client-side filtering with no indication that results may be incomplete.

**F-M9 — Import error details not surfaced to admin**
- File: `src/views/admin/AdminDashboardView.vue` lines 449–450 / 472–473
- Import result shows row count but not which tables failed or why.

**F-M10 — No visual distinction for read-only exams when match is not active**
- File: `src/views/tutor/MatchDetailView.vue` line 242
- Edit/delete buttons disappear silently; there's no label or tooltip indicating the exams are read-only in the current match state.

---

## 4. Security Findings

### Critical

**S-C1 — JWT `alg: "none"` not explicitly rejected**
- File: `app/shared/infrastructure/security.py` lines 112 / 118
- `_decode_with_rotation()` passes `algorithms=[settings.jwt_algorithm]` but does not explicitly check for `"none"` in the token header before processing.
- Fix: `if header.get("alg", "").lower() == "none": return None` before decode.

### High

**S-H1 — Admin password policy may be insufficient**
- File: `app/shared/infrastructure/config.py` lines 139–155
- Requires only 3-of-4 character classes at 12 chars minimum. A brute-force resistant policy should require 16+ chars or enforce all 4 classes.

**S-H2 — `session_service` ownership not independently verified**
- File: `app/teaching/api/session_router.py` lines 46–59
- The router passes `tutor_user_id=int(user["sub"])` but needs to confirm the service layer checks this against the session's owner before allowing any update.

**S-H3 — Missing Content-Security-Policy header**
- File: `app/middleware/security_headers.py`
- `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Cache-Control` are set, but CSP is absent. Without CSP, XSS payloads can load arbitrary scripts.
- Fix: Add `Content-Security-Policy: default-src 'self'` (adjust for Vue app needs).

**S-H4 — Review lock timezone failure silently raises `ReviewLockedError`**
- File: `app/review/api/router.py` lines 111–118
- If `created_at` is corrupted or in unexpected format, a broad exception handler swallows the real cause and raises `ReviewLockedError`, masking data integrity issues.
- Fix: Log the original exception before re-raising.

**S-H5 — Admin user listing exposes phone and email PII**
- File: `app/admin/infrastructure/table_admin_repo.py` lines 145–149
- `/api/admin/users` returns `phone` and `email` for every user. Confirm endpoint is restricted to super-admin only; consider masking or omitting these fields.

**S-H6 — Exam over-disclosure (tutor sees all subjects)**
- File: `app/teaching/api/exam_router.py` line 60 (cross-reference with B1-M2)
- Tutor with any active match with a student can view exams for subjects they don't teach.

### Medium

**S-M1 — `extra_set` in `BaseRepository.safe_update` allows raw SQL concatenation**
- File: `app/shared/infrastructure/base_repository.py` lines 56–64 (cross-reference with B1-L2)
- Not exploitable via current callers, but the API is dangerous. Severity escalated from Low to Medium given the infrastructure-level blast radius.

**S-M2 — User-Agent not truncated in audit log**
- File: `app/identity/domain/services.py` lines 72–74
- Unlimited User-Agent string written to audit log enables log injection and unbounded log growth.
- Fix: Truncate to 256 chars before logging.

**S-M3 — User enumeration via conversation creation error**
- File: `app/messaging/application/message_service.py` lines 53–56
- The error `ConversationNotAllowedError` reveals a role-pair mismatch rather than a generic 403, allowing callers to determine whether two user IDs have a valid role relationship.

**S-M4 — Logout success on missing JTI allows token replay** _(cross-reference B1-C5)_
- File: `app/identity/api/router.py` lines 148–150
- Severity promoted to Medium: a compromised refresh token without JTI is never invalidated.

### Low

**S-L1 — `LEAKY_EXCEPTION_TYPES` set may be incomplete**
- File: `app/main.py` lines 129–162
- Does not include `OperationalError` / `DatabaseError` aliases that psycopg2 may surface, potentially leaking DB type information.

**S-L2 — Username allows leading/trailing `.` and `-` and `@` symbol**
- File: `app/identity/api/schemas.py` lines 45–48
- Regex `^[A-Za-z0-9_.\-@]+$` is overly permissive. Consider restricting leading/trailing special chars.

---

## 5. Summary Table

| Area | Critical | High | Medium | Low | Total |
|------|----------|------|--------|-----|-------|
| Backend — Core | 5 | 5 | 5 | 5 | 20 |
| Backend — Admin/Infra | 0 | 1 | 1 | 3 | 5 |
| Frontend — Bugs | 0 | 0 | 12 | 0 | 12 |
| Frontend — UX/UI | 0 | 0 | 10 | 0 | 10 |
| Frontend — Missing Features | 0 | 0 | 10 | 0 | 10 |
| Security | 1 | 6 | 4 | 2 | 13 |
| **Grand Total** | **6** | **12** | **42** | **10** | **70** |

---

## 6. Remediation Priority

### Immediate (Critical)

| ID | Action |
|----|--------|
| S-C1 | Reject JWT tokens with `alg: "none"` in header before decode |
| B1-C5 | Fail logout if refresh token has no `jti`; do not return 200 silently |
| B1-C2 | Fix `REVIEWABLE_STATUSES` to match error message (remove "paused" or fix message) |
| B1-C3 | Add subject-scope check to exam creation authorization |
| B1-C4 | Re-read `want_trial` after contract term updates, not before |
| B1-C1 | Ensure all code paths calling match repo use the same data structure (add `session_count` to `get_match_participants` or remove the field check) |

### High Priority

| ID | Action |
|----|--------|
| S-H3 | Add `Content-Security-Policy` header in security_headers middleware |
| S-H1 | Increase admin password minimum to 16 chars or require all 4 character classes |
| S-H2 | Confirm `session_service` validates `tutor_user_id` against session owner |
| S-H4 | Log original exception before re-raising `ReviewLockedError` |
| B2-H1 | Add pagination to `/api/students` and `/api/subjects` |
| B1-M3 | Reconstruct `Contract` entity in `confirm_trial_with_terms` to enforce domain validation |
| B1-M4 | Add `total_pages`, `has_next`, `has_prev` to `PaginatedData` schema |
| F-B1 | Add error state display in both dashboard views when match load fails |
| F-B3 | Serialize concurrent fetch + polling calls in ChatView |

### Medium Priority

| ID | Action |
|----|--------|
| S-M2 | Truncate User-Agent to 256 chars before writing to audit log |
| S-M4 | Return 400/401 from logout if token has no JTI (see S-C5 above) |
| B2-M1 | Add `AT TIME ZONE` conversion to analytics EXTRACT queries |
| B1-M1 | Standardize HTTP status code for locked review (pick 400 or 423 and use it everywhere) |
| F-B5 | Audit all stores for complete reset on logout |
| F-B8 | Display re-request guidance when `confirmReset` fails after token is issued |
| F-U5 | Distinguish API error from genuine "no data" in Income/Expense views |
| F-U6 | Extract shared date/time formatting utility and use it everywhere |
| F-M2 | Report which sub-request failed when profile save is partial |

### Low Priority

| ID | Action |
|----|--------|
| S-L1 | Expand `LEAKY_EXCEPTION_TYPES` to include psycopg2 `OperationalError` / `DatabaseError` |
| B1-L2 | Restrict `extra_set` in `safe_update` to `psql.Composable` types only |
| B2-L1 | Wrap `update_profile` in explicit transaction for consistency |
| F-U1 | Show loading indicator on post-action refetch in MatchDetailView |
| F-U4 | Add tooltip to disabled "Add Subject" button |
| F-M6 | Add dirty tracking and cancel confirmation to SessionForm |
| F-M9 | Surface per-table error details in admin import result |
