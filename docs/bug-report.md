# Bug Report — Tutor Matching and Rating Platform (TMRP)

**Date:** 2026-04-06  
**Scope:** Full codebase review — `tutor-platform-api` (Python/FastAPI) and `tutor-platform-web` (Vue.js/Vite)  
**Total Issues Found:** 40

---

## Severity Legend

| Level | Meaning |
|-------|---------|
| **Critical** | Causes complete feature failure or immediate security breach |
| **High** | Significant security risk or data corruption potential |
| **Medium** | Incorrect behavior, data inconsistency, or poor security posture |
| **Low** | Edge case bugs, minor inconsistencies, or dead code |

---

## Critical

### BUG-01 — Catch-all route defined before root redirect (route unreachable)

- **File:** `tutor-platform-web/src/router/index.js:63–73`
- **Description:** The catch-all route `/:pathMatch(.*)*` is defined **before** the `/` root redirect. Vue Router matches routes in definition order, so `/:pathMatch(.*)*` matches every path including `/`, making the root redirect permanently unreachable. Users navigating to `/` are always redirected to `/login` regardless of authentication state, bypassing the role-based redirect logic entirely.
- **Fix:** Move the catch-all route to the very end of the route definitions.

---

## High

### BUG-02 — Route guard bypassed for all child routes (auth/role checks ineffective)

- **File:** `tutor-platform-web/src/router/index.js:82–101`
- **Description:** The `beforeEach` guard checks `to.meta.requiresAuth` and `to.meta.role`. However, child routes do not define their own `meta` objects and Vue Router does not automatically merge parent `meta` into `to.meta` for the leaf route. As a result, `to.meta.requiresAuth` and `to.meta.role` are both `undefined` for every child route, and **all authentication and role-based access guards are silently bypassed**. An unauthenticated user can navigate directly to any protected child route URL.
- **Fix:** Replace `to.meta.requiresAuth` with `to.matched.some(record => record.meta.requiresAuth)` and `to.meta.role` with `to.matched.find(record => record.meta.role)?.meta.role`.

### BUG-03 — SQL injection vector in `update_visibility()` (no column name validation)

- **File:** `tutor-platform-api/app/repositories/tutor_repo.py:125–134`
- **Description:** Column names from the `flags` dict keys are interpolated directly into SQL via an f-string (`f"{col} = ?"`) with no whitelist validation. All other repository methods use `validate_columns()` with an `ALLOWED_COLUMNS` set, but this method does not. While currently protected at the router layer by Pydantic, the repository itself has no defense — any future call site bypassing Pydantic would be a critical SQL injection vulnerability.
- **Fix:** Add an `ALLOWED_COLUMNS` set and call `validate_columns(flags.keys(), ALLOWED_COLUMNS)` at the start of the method.

### BUG-04 — SQL injection vector in `update_profile()` (no column name validation)

- **File:** `tutor-platform-api/app/repositories/tutor_repo.py:136–149`
- **Description:** Same issue as BUG-03. The `update_profile` method builds SQL column names from `**fields` keyword argument keys with no whitelist validation.
- **Fix:** Same as BUG-03 — add and enforce `ALLOWED_COLUMNS`.

### BUG-05 — Privilege escalation via unrestricted `role` field in registration

- **File:** `tutor-platform-api/app/models/auth.py:6–10`
- **Description:** The `RegisterRequest` model accepts any arbitrary string for the `role` field. A malicious user could submit `role="admin"` during registration and potentially gain admin privileges if the value is inserted into the database without further sanitization. The field should be restricted at the model level.
- **Fix:** Change the `role` field type to `Literal["parent", "tutor"]`.

### BUG-06 — Missing `rollback` in `register_user()` on multi-step transaction failure

- **File:** `tutor-platform-api/app/repositories/auth_repo.py:41–52`
- **Description:** `register_user` performs two sequential INSERTs (into `Users`, then optionally into `Tutors`) followed by a single `commit`. There is no `try/except` with `conn.rollback()`. If the second INSERT fails (e.g., due to a constraint violation in `Tutors`), the first INSERT may be left in an inconsistent state, potentially creating an orphaned `Users` record.
- **Fix:** Wrap both INSERTs in a `try/except` block with `self.conn.rollback()` in the `except` clause, mirroring the pattern used in `tutor_repo.py`'s `replace_subjects()`.

### BUG-07 — Pending requests never rejected when token refresh fails (promise leak)

- **File:** `tutor-platform-web/src/api/index.js:47–76`
- **Description:** When a token refresh is in progress, subsequent 401 requests are queued in `pendingRequests`. On refresh success, the queue is flushed via `onRefreshed()`. However, on refresh failure, `auth.logout()` is called but `pendingRequests` is never drained with rejections. All queued promises remain permanently pending, causing a memory leak and leaving callers in a hung state.
- **Fix:** In the `catch` block of the refresh logic, iterate over `pendingRequests` and call `reject(error)` on each before clearing the array.

---

## Medium

### BUG-08 — `import-all` endpoint missing `_coerce_value()` — booleans stored as strings

- **File:** `tutor-platform-api/app/routers/admin.py:370`
- **Description:** In the `/import-all` endpoint, CSV row values are inserted without calling `_coerce_value()`: `values = tuple(row[c] for c in columns)`. The single `/import` endpoint correctly calls `_coerce_value()`. This means boolean columns (e.g., `want_trial`, `visible_to_parent`) are stored as the string `"True"`/`"False"` instead of MS Access BIT values `-1`/`0`, causing data corruption.
- **Fix:** Change the tuple comprehension to `tuple(_coerce_value(row[c]) for c in columns)`.

### BUG-09 — `import-all` with `clear_first` has no rollback — partial data deletion unrecoverable

- **File:** `tutor-platform-api/app/routers/admin.py:341–375`
- **Description:** The `clear_first` DELETE statements are executed via `repo.execute()`, which calls `conn.commit()` internally after each statement. The subsequent INSERT phase is committed separately at the end. If the INSERT phase fails partway, the DELETE commits cannot be rolled back, leaving the database permanently empty for the affected tables.
- **Fix:** Wrap the entire clear + insert operation in a single explicit transaction using `conn.begin()` / `conn.rollback()` instead of relying on `repo.execute()` auto-commits.

### BUG-10 — Admin users cannot perform match status operations (inconsistent authorization)

- **File:** `tutor-platform-api/app/routers/matches.py:159`
- **Description:** The `update_match_status` authorization check is `if not is_parent and not is_tutor: raise ForbiddenException`. Unlike `get_match_detail` (line 129) and `list_matches` (line 99), which both include an `is_admin` branch, the status update endpoint blocks admins from intervening in match status transitions.
- **Fix:** Add `and not is_admin(user)` to the authorization check, consistent with other endpoints.

### BUG-11 — Session update and edit-log writes are non-atomic (partial audit trail on failure)

- **File:** `tutor-platform-api/app/routers/sessions.py:111–116`
- **Description:** The session `UPDATE` and subsequent `INSERT` into the edit-log table are each committed separately via `BaseRepository.execute()`. If the process is interrupted between the update commit and an edit-log insert, the database will contain updated data with an incomplete or missing audit trail.
- **Fix:** Use an explicit transaction (via `database_tx`) to wrap the update and all edit-log inserts in a single atomic operation.

### BUG-12 — `rate_asc` sort uses sum of rates instead of average (inconsistent with filter logic)

- **File:** `tutor-platform-api/app/routers/tutors.py:92–96`
- **Description:** The `rate_asc` sort key computes `sum(s["hourly_rate"] for s in subjects)`. A tutor teaching three subjects at 300/hr each will sort higher (sum=900) than a tutor teaching one subject at 500/hr (sum=500), despite having a lower per-subject rate. The filter logic at lines 63–69 correctly uses `avg_rate = sum(rates) / len(rates)`.
- **Fix:** Change the sort key to use the average: `sum(rates) / len(rates)` where `rates` is the filtered list of non-null hourly rates.

### BUG-13 — Refresh tokens never invalidated after use (stolen tokens reusable indefinitely)

- **File:** `tutor-platform-api/app/routers/auth.py:62–72`
- **Description:** The `/refresh` endpoint issues a new access token and refresh token but never invalidates the old refresh token. A stolen refresh token can be used to generate new access tokens until it naturally expires, with no way to revoke it.
- **Fix:** Implement token rotation (store issued refresh tokens and invalidate on use) or maintain a token blacklist.

### BUG-14 — `decode_access_token` accepts tokens with missing `type` claim

- **File:** `tutor-platform-api/app/utils/security.py:51–61`
- **Description:** The function rejects tokens where `payload.get("type") == "refresh"` but accepts any other value, including no `type` field at all. A token crafted without a `type` claim (or with `type="anything_else"`) would be accepted as a valid access token.
- **Fix:** Change the check to a positive assertion: `if payload.get("type") != "access": raise credentials_exception`.

### BUG-15 — `assert` used for status validation — disabled by Python's `-O` flag

- **File:** `tutor-platform-api/app/repositories/match_repo.py:75`
- **Description:** `assert new_status in self.VALID_STATUSES` is used to validate the status parameter. Python's `assert` statements are compiled out when running with the `-O` (optimize) flag, which would silently disable this check in production if optimization is enabled.
- **Fix:** Replace with `if new_status not in self.VALID_STATUSES: raise ValueError(f"Invalid status: {new_status}")`.

### BUG-16 — Rate limiter has unbounded memory growth (IP entries never evicted)

- **File:** `tutor-platform-api/app/middleware/rate_limit.py:23, 31–33`
- **Description:** The `self.attempts` dictionary stores an entry per unique `path + IP` combination. While stale timestamps within a window are pruned, the dictionary keys are never evicted. Under sustained internet traffic (bots, scanners), this dict grows without bound and will eventually exhaust server memory.
- **Fix:** Add a TTL-based eviction step: after pruning timestamps, remove the key entirely if the bucket becomes empty.

### BUG-17 — `write_csv` has no path traversal protection

- **File:** `tutor-platform-api/app/utils/csv_handler.py:16–27`
- **Description:** `read_csv` validates that the resolved path is under the `data/` directory, but `write_csv` has no equivalent check. An attacker-controlled `file_path` argument could write to arbitrary filesystem locations.
- **Fix:** Add the same `resolved_path.is_relative_to(base_dir)` guard to `write_csv` that exists in `read_csv`.

### BUG-18 — `AvailabilitySlot` time fields accept invalid values (e.g., `99:99`)

- **File:** `tutor-platform-api/app/models/tutor.py:27–30`
- **Description:** The regex `^\d{2}:\d{2}(:\d{2})?$` accepts nonsensical times like `99:99` or `25:61`. Additionally, there is no validation that `start_time < end_time`, so a slot with `start_time="18:00"` and `end_time="08:00"` would be accepted.
- **Fix:** Add a Pydantic validator that parses the time strings and checks `start_time < end_time`.

### BUG-19 — Scheduled tasks use naive `datetime.now()` instead of UTC-aware datetime

- **File:** `tutor-platform-api/app/tasks/scheduled.py:33`
- **Description:** `datetime.now()` returns a naive (timezone-unaware) local datetime. JWT tokens in `security.py` use `datetime.now(timezone.utc)`. If the server runs in a non-UTC timezone, the scheduled task's datetime comparisons will be offset by the timezone difference, causing reviews to be locked at the wrong time.
- **Fix:** Replace `datetime.now()` with `datetime.now(timezone.utc)` throughout all task files.

### BUG-20 — `TutorProfileUpdate` boolean fields default to `True` instead of `None` (unintended overwrites)

- **File:** `tutor-platform-api/app/models/tutor.py:11–15`
- **Description:** Visibility boolean fields (`show_university`, `show_department`, etc.) have `default=True`. When used with `model_dump(exclude_unset=True)`, a partial update request that doesn't include these fields correctly excludes them. However, because the fields are typed as `bool` (not `Optional[bool]`), any client submitting a full form will always include them and may inadvertently reset all visibility flags to `True`.
- **Fix:** Change the field types to `Optional[bool] = None` so that unset fields are cleanly excluded.

### BUG-21 — `visible_to_parent` reset to `false` after exam form submission

- **File:** `tutor-platform-web/src/views/tutor/MatchDetailView.vue:323, 399`
- **Description:** The `examForm` reactive object initializes `visible_to_parent: true`, but the post-submission reset sets it to `false`. All subsequent exam submissions will default to not visible to parents unless the user manually toggles the checkbox each time.
- **Fix:** Change the reset line to `examForm.visible_to_parent = true` to match the initial default.

### BUG-22 — Termination reason not cleared when `ContractForm` is reopened

- **File:** `tutor-platform-web/src/components/match/ContractForm.vue:27–44`
- **Description:** Parent views cancel the termination dialog by setting `showTerminate = false` but never call the component's `reset()` method. If the user opens, types a reason, cancels, and reopens the form, the previous reason text is still present.
- **Fix:** Call `contractFormRef.value.reset()` in the cancel handler and after a successful termination.

### BUG-23 — `ProgressChart` date sorting is fragile across browsers

- **File:** `tutor-platform-web/src/components/stats/ProgressChart.vue:51`
- **Description:** Dates are first converted to zh-TW locale strings (e.g., `"2026/4/6"`) and then sorted with `new Date(a) - new Date(b)`. The `new Date()` constructor's behavior with locale-formatted strings is implementation-dependent and may produce `NaN` in some browsers, causing the sort to produce incorrect or random order.
- **Fix:** Sort on the original ISO date strings before converting to locale format for display.

### BUG-24 — Token validation race condition on page load (protected views render before auth check)

- **File:** `tutor-platform-web/src/App.vue:29–38`
- **Description:** On page load, the router guard executes synchronously and allows access to protected routes because `auth.isLoggedIn` is `true` based on the value in `localStorage`. The async `authApi.getMe()` call in `onMounted` that validates the token against the server has not yet completed. Protected views render and fire their own `onMounted` API calls before the token is confirmed valid, resulting in multiple 401 errors and a flash of protected content before redirect.
- **Fix:** Delay initial navigation until `getMe()` resolves, or initialize `isLoggedIn` to `false` and only set it to `true` after a successful `getMe()` response.

### BUG-25 — `InviteForm` blocks submission when `hourly_rate` is `0` (free sessions impossible)

- **File:** `tutor-platform-web/src/components/match/InviteForm.vue:81–91`
- **Description:** The form initializes `hourly_rate: 0` and the submit guard checks `!form.hourly_rate`. Since `!0` is `true`, free tutoring sessions can never be submitted — the validation always fires. Additionally, the hourly rate is not auto-populated when the user selects a subject.
- **Fix:** Change the validation to `form.hourly_rate === null || form.hourly_rate === undefined` (or `form.hourly_rate < 0`). Consider auto-populating the rate when a subject is selected.

### BUG-26 — `TutorCard` displays `$null/hr` when hourly rate is hidden by tutor

- **File:** `tutor-platform-web/src/components/tutor/TutorCard.vue:14`
- **Description:** When a tutor sets `show_hourly_rate: false`, the API returns `null` for the `hourly_rate` field. The template renders `${{ tutor.subjects[0].hourly_rate }}/hr` without a null check, resulting in the string `$null/hr` being displayed to the parent.
- **Fix:** Add a conditional: `{{ tutor.subjects[0].hourly_rate != null ? '$' + tutor.subjects[0].hourly_rate + '/hr' : 'Rate hidden' }}`.

---

## Low

### BUG-27 — Single `/import` endpoint has no rollback on partial row insertion failure

- **File:** `tutor-platform-api/app/routers/admin.py:127–131`
- **Description:** Rows are inserted one by one in a loop. If an exception occurs mid-loop, there is no rollback, leaving the table partially populated.
- **Fix:** Wrap the insertion loop in a `try/except` with `conn.rollback()`.

### BUG-28 — Pickle deserialization of Huey task results (theoretical RCE risk)

- **File:** `tutor-platform-api/app/routers/admin.py:291`
- **Description:** `pickle.loads(raw)` is used to deserialize task results from SQLite storage (marked `# nosec`). While restricted to admin users, `pickle` deserialization is inherently dangerous — a compromised SQLite file would allow arbitrary code execution.
- **Fix:** Use a safer serialization format such as `json` for task results where possible.

### BUG-29 — `disagree_terminate` previous status parsing fragile on corrupted DB data

- **File:** `tutor-platform-api/app/routers/matches.py:193–199`
- **Description:** The `termination_reason` field encodes `previous_status|reason`. If the database is manually edited and the field lacks the `|` separator, the fallback defaults to `"active"`, which may be incorrect.
- **Fix:** Already has a defensive fallback (`if previous_status not in ("active", "paused"): previous_status = "active"`), but consider logging a warning when the fallback is triggered.

### BUG-30 — `_parse_month` does not validate year value

- **File:** `tutor-platform-api/app/routers/stats.py:15`
- **Description:** Month is validated to be between 1 and 12, but year is not validated. Values like `"0000-01"` or `"9999-12"` pass the regex and proceed without error.
- **Fix:** Add a year range check, e.g., `2000 <= year <= 2100`.

### BUG-31 — Aggregate functions return `None` when no matching sessions exist

- **File:** `tutor-platform-api/app/repositories/stats_repo.py:12–26, 48–63`
- **Description:** `SUM()` in MS Access returns `NULL` when there are no rows. The returned dict may have `None` values for `total_income`, `total_hours`, etc., causing a `TypeError` in callers that perform arithmetic on these values.
- **Fix:** Use `NZ(SUM(...), 0)` (MS Access syntax) or add `or 0` guards in the callers.

### BUG-32 — `if subject_id:` incorrectly treats `subject_id=0` as absent

- **File:** `tutor-platform-api/app/repositories/stats_repo.py:108`
- **Description:** The condition `if subject_id:` treats `0` as falsy, skipping the subject filter. Should be `if subject_id is not None:`.
- **Fix:** Change to `if subject_id is not None:`.

### BUG-33 — `get_connection` returns `None` when `retries=0`

- **File:** `tutor-platform-api/app/database.py:22–31`
- **Description:** If `retries` is `0`, the `for attempt in range(retries)` loop body never executes and the function implicitly returns `None`. Callers expect a `pyodbc.Connection` and will crash.
- **Fix:** Add a guard: `if retries <= 0: raise ValueError("retries must be > 0")`.

### BUG-34 — Rate limiter is not async-safe (concurrent requests can exceed limit)

- **File:** `tutor-platform-api/app/middleware/rate_limit.py:30–40`
- **Description:** The `self.attempts` dict is read and mutated without any lock. Under concurrent async requests, two coroutines can simultaneously read the same bucket, both see `len(bucket) < max_attempts`, and both append — allowing more requests through than the configured limit.
- **Fix:** Use an `asyncio.Lock` per bucket key to serialize access during the check-and-append operation.

### BUG-35 — `MatchCreate.hourly_rate` allows zero and negative values

- **File:** `tutor-platform-api/app/models/match.py:8`
- **Description:** No minimum constraint on `hourly_rate`. A match with a zero or negative rate could be created, unlike `SubjectItem.hourly_rate` in `tutor.py` which correctly uses `gt=0`.
- **Fix:** Add `gt=0` constraint: `hourly_rate: float = Field(..., gt=0)`.

### BUG-36 — `ExamCreate.score` allows negative values

- **File:** `tutor-platform-api/app/models/exam.py:11`
- **Description:** No minimum constraint on `score`. A negative exam score could be submitted.
- **Fix:** Add `ge=0` constraint: `score: float = Field(..., ge=0)`.

### BUG-37 — `SessionCreate.hours` allows zero and negative values

- **File:** `tutor-platform-api/app/models/session.py:9`
- **Description:** No minimum constraint on `hours`. A session with zero or negative hours corrupts income/expense statistics.
- **Fix:** Add `gt=0` constraint: `hours: float = Field(..., gt=0)`.

### BUG-38 — CSV header whitespace not stripped before column name validation

- **File:** `tutor-platform-api/app/tasks/import_export.py:44`
- **Description:** Python's `csv.DictReader` does not strip whitespace from header names. A CSV file with headers like `" tutor_id"` (leading space) would fail the `_SAFE_COLUMN` regex and produce a confusing error rather than cleanly importing.
- **Fix:** Strip whitespace from headers when constructing the `DictReader`, e.g., `fieldnames=[h.strip() for h in reader.fieldnames]`.

### BUG-39 — `handleImportAll` reduce crashes or produces wrong result with non-numeric API values

- **File:** `tutor-platform-web/src/views/admin/AdminDashboardView.vue:252–253`
- **Description:** `Object.values(result).reduce((a, b) => a + b, 0)` assumes all values in the result object are numbers. If the API includes a string field (e.g., `task_id`), the reduce produces a concatenated string instead of a number.
- **Fix:** Filter for numeric values: `Object.values(result).filter(v => typeof v === 'number').reduce((a, b) => a + b, 0)`.

### BUG-40 — `ReviewForm.vue` and `MatchStatusBadge.vue` are fully implemented but never used (dead code)

- **File:** `tutor-platform-web/src/components/review/ReviewForm.vue`, `tutor-platform-web/src/components/match/MatchStatusBadge.vue`
- **Description:** Both components are fully implemented but not imported by any view or component. Parent views have inline review form implementations instead of using `ReviewForm.vue`. `MatchStatusBadge.vue` duplicates the functionality of `StatusBadge.vue`.
- **Fix:** Either integrate `ReviewForm.vue` in place of the inline implementations, or remove both unused files.

---

## Summary Table

| ID | File | Line(s) | Severity |
|----|------|---------|----------|
| BUG-01 | `src/router/index.js` | 63–73 | **Critical** |
| BUG-02 | `src/router/index.js` | 82–101 | **High** |
| BUG-03 | `repositories/tutor_repo.py` | 125–134 | **High** |
| BUG-04 | `repositories/tutor_repo.py` | 136–149 | **High** |
| BUG-05 | `models/auth.py` | 6–10 | **High** |
| BUG-06 | `repositories/auth_repo.py` | 41–52 | **High** |
| BUG-07 | `src/api/index.js` | 47–76 | **High** |
| BUG-08 | `routers/admin.py` | 370 | **Medium** |
| BUG-09 | `routers/admin.py` | 341–375 | **Medium** |
| BUG-10 | `routers/matches.py` | 159 | **Medium** |
| BUG-11 | `routers/sessions.py` | 111–116 | **Medium** |
| BUG-12 | `routers/tutors.py` | 92–96 | **Medium** |
| BUG-13 | `routers/auth.py` | 62–72 | **Medium** |
| BUG-14 | `utils/security.py` | 51–61 | **Medium** |
| BUG-15 | `repositories/match_repo.py` | 75 | **Medium** |
| BUG-16 | `middleware/rate_limit.py` | 23, 31–33 | **Medium** |
| BUG-17 | `utils/csv_handler.py` | 16–27 | **Medium** |
| BUG-18 | `models/tutor.py` | 27–30 | **Medium** |
| BUG-19 | `tasks/scheduled.py` | 33 | **Medium** |
| BUG-20 | `models/tutor.py` | 11–15 | **Medium** |
| BUG-21 | `views/tutor/MatchDetailView.vue` | 323, 399 | **Medium** |
| BUG-22 | `components/match/ContractForm.vue` | 27–44 | **Medium** |
| BUG-23 | `components/stats/ProgressChart.vue` | 51 | **Medium** |
| BUG-24 | `src/App.vue` | 29–38 | **Medium** |
| BUG-25 | `components/match/InviteForm.vue` | 81–91 | **Medium** |
| BUG-26 | `components/tutor/TutorCard.vue` | 14 | **Medium** |
| BUG-27 | `routers/admin.py` | 127–131 | **Low** |
| BUG-28 | `routers/admin.py` | 291 | **Low** |
| BUG-29 | `routers/matches.py` | 193–199 | **Low** |
| BUG-30 | `routers/stats.py` | 15 | **Low** |
| BUG-31 | `repositories/stats_repo.py` | 12–26, 48–63 | **Low** |
| BUG-32 | `repositories/stats_repo.py` | 108 | **Low** |
| BUG-33 | `app/database.py` | 22–31 | **Low** |
| BUG-34 | `middleware/rate_limit.py` | 30–40 | **Low** |
| BUG-35 | `models/match.py` | 8 | **Low** |
| BUG-36 | `models/exam.py` | 11 | **Low** |
| BUG-37 | `models/session.py` | 9 | **Low** |
| BUG-38 | `tasks/import_export.py` | 44 | **Low** |
| BUG-39 | `views/admin/AdminDashboardView.vue` | 252–253 | **Low** |
| BUG-40 | `ReviewForm.vue`, `MatchStatusBadge.vue` | entire file | **Low** |

---

## Recommended Fix Priority

### Priority 1 — Fix immediately
- **BUG-02** Route guard bypass (all auth checks ineffective on child routes)
- **BUG-05** Privilege escalation via unrestricted `role` field
- **BUG-03 / BUG-04** SQL injection vectors in tutor repository

### Priority 2 — Fix before next release
- **BUG-01** Catch-all route ordering (root redirect dead)
- **BUG-06** Missing rollback in `register_user`
- **BUG-07** Hanging promises on token refresh failure
- **BUG-14** Overly permissive token type validation
- **BUG-13** Refresh tokens never invalidated

### Priority 3 — Schedule for near-term sprint
All remaining Medium severity bugs (BUG-08 through BUG-26).

### Priority 4 — Fix when convenient
All Low severity bugs (BUG-27 through BUG-40).
