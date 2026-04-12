# Separation-of-Concerns & Technical-Debt Audit

**Project:** TMRP — Tutor Matching and Rating Platform
**Audit date:** 2026-04-12
**Scope:** `tutor-platform-api/`, `tutor-platform-web/`, `docs/`, `docker-compose.yml`, `.sixth/`
**Baseline:** post-commit `19e897f`. The 28-item systematic bug audit (`92d3e16`) is assumed applied; this document focuses on **structural / design debt**, not the bugs already resolved there.

---

## Executive summary

The recent DDD restructure (commit `92d3e16`) established the target architecture — bounded contexts under `app/<bc>/{api,application,domain,infrastructure}/` — but the migration was **left half-finished**. Three self-reinforcing problems dominate the remaining debt:

1. **The legacy flat layer (`app/routers/`, `app/repositories/`, `app/models/`) is still shipped** and is the *only* layer the test suite exercises. `app/main.py` no longer wires these routers in, yet they cannot be deleted because every test in `tests/` patches them.
2. **The new BC layer has zero automated test coverage.** The production code path (services, domain entities, state machines, new routers) is unverified. CI validates dead code.
3. **Repositories return raw `dict`s and the routers do the last-mile shaping**, so DB column names leak into HTTP responses and "small" transformations (visibility masking, float coercion) are duplicated 2–3 times across layers.

Nothing below is a correctness bug in the "crash the server" sense — the 28-bug audit already covered those. What remains is the cost of change: touching one concern currently means touching three files.

**Priority-ordered fix list** (see §Recommendations for detail):

1. Migrate `tests/` to target the new BC routers/services → unblocks legacy deletion.
2. Delete `app/routers/`, `app/repositories/`, `app/models/`, and the five shim re-exports.
3. Map repository rows to DTOs at the infrastructure boundary; remove router-side masking.
4. Centralise magic numbers (`max_students=5`, `review_lock_days`, `PAGE_SIZE`) in `shared/infrastructure/config.py` or a `constants.py`.
5. Extract an analytics application service; stop letting routers call repositories directly.
6. Wire dependencies through FastAPI `Depends` factories instead of per-file `_build_service(conn)` helpers.

---

## Part 1 — Separation of concerns

### Critical

#### SoC-C1. Legacy layer still live in the test suite
**Files:** `tutor-platform-api/app/routers/*.py`, `app/repositories/*.py`, `app/models/*.py`, `tests/test_*.py`
**Evidence:**
- `app/routers/__init__.py:2-32` emits a `DeprecationWarning` and documents: *"tests/ 仍 patch 此處模組做為單元測試的隔離點, 完整移除前需先遷移測試"*.
- `app/main.py:18-29` imports only the new BC routers.
- `tests/test_matches.py:38-40` patches `app.routers.matches.StudentRepository`, `app.routers.matches.TutorRepository`, `app.routers.matches.MatchRepository` — i.e., the deprecated classes.

**Impact:** Green CI does not indicate the shipping code works. Every test currently validates a code path `main.py` refuses to load.

#### SoC-C2. Application service holds a raw DB connection and drives transactions
**File:** `tutor-platform-api/app/matching/application/match_app_service.py:22-32, 150`
**Evidence:**
```python
def __init__(self, match_repo: IMatchRepository, catalog: ICatalogQuery, conn):
    self._match_repo = match_repo
    self._catalog = catalog
    self._conn = conn                # ← infra primitive inside application layer
...
with transaction(self._conn):        # ← service owns the tx boundary
```
**Impact:** Breaks the repository abstraction — swapping Postgres for another store would require rewriting the service, not just the infrastructure layer. The `conn` parameter also makes the service untestable without a real/mock psycopg2 connection.
**Fix sketch:** Introduce a `UnitOfWork` port in `matching/domain/ports.py` and inject an implementation; remove `conn` from the service signature.

#### SoC-C3. Raw SQL and cursor operations inside HTTP handlers
**File:** `tutor-platform-api/app/admin/api/router.py`
**Evidence:**
- `lines 121-130` (import_csv): builds `INSERT INTO {table} ...` as an f-string, gets `conn.cursor()`, iterates rows, calls `conn.commit()` / `conn.rollback()` directly in the endpoint.
- `lines 162-178` (reset_database): same pattern — router holds the delete loop, the savepoint logic, and the commit boundary.
- `lines 274-315` (import_all): transaction, savepoint-per-row retry, and serial-sequence reset all live in the router body.

**Impact:** The admin router is a ~320-line mini-ORM. Any change to CSV rules, table list, or transactional semantics requires editing a route handler.
**Fix sketch:** Introduce `app/admin/application/import_service.py` and `app/admin/infrastructure/csv_importer.py`; the router should only parse the upload and return an `ApiResponse`.

#### SoC-C4. Router repeats logic already present in the domain service
**File:** `tutor-platform-api/app/catalog/api/tutor_router.py:54-64, 136-142`
**Evidence:** `search_tutors` strips `hourly_rate` from each subject and clears `subjects` based on visibility flags **before** calling `service.apply_visibility(t)`. `get_tutor_detail` repeats the same masking inline at lines 137-141, then also calls `service.apply_visibility(tutor)`. The same function exists in three locations: the catalog service, this router (twice), and the deprecated `app/routers/tutors.py:13-24`.

**Impact:** When a privacy rule changes (e.g., a new `show_school` flag), four places need to stay in sync. This is exactly the scenario DDD was meant to prevent.
**Fix sketch:** Move all masking into `catalog/domain/services.py::apply_visibility`; delete router-side branches.

#### SoC-C5. Router reaches into the infrastructure layer for ad-hoc queries
**File:** `tutor-platform-api/app/catalog/api/tutor_router.py:89-95`
**Evidence:** `update_subjects` performs a function-local import of `BaseRepository` and runs `SELECT subject_id FROM subjects` inline — despite `PostgresTutorRepository` already being injected.
```python
from app.shared.infrastructure.base_repository import BaseRepository
base = BaseRepository(conn)
all_subjects = base.fetch_all("SELECT subject_id FROM subjects")
```
**Impact:** Subject-catalog concerns leak into the tutor router; infrastructure is instantiated from within a request handler; the lazy import hides the dependency from static analysis.
**Fix sketch:** Add `list_subject_ids()` to `PostgresSubjectRepository` (or a `SubjectCatalogQuery` port) and inject it.

#### SoC-C6. HTTP response shape is the domain entity shape
**File:** `tutor-platform-api/app/matching/application/match_app_service.py:84-112`
**Evidence:** `get_detail` hand-builds a 28-field `dict` by copying attributes off the `Match` entity. The comment on line 83 is explicit: *"保留所有 m.* 欄位以維持 API 相容性"* ("preserve all m.* fields for API compatibility"). Any rename on `Match` either breaks the API or requires a field alias here.
**Impact:** There is no API DTO boundary. Frontend contract and domain model evolve as one.
**Fix sketch:** Introduce `matching/api/schemas.py::MatchDetailResponse` (Pydantic) and map once.

### Moderate

#### SoC-M1. Duplicate-username pre-check in the identity router
**File:** `tutor-platform-api/app/identity/api/router.py:33-36` and `app/identity/application/services.py:35`
**Evidence:** The router catches a `DuplicateUsernameError` and then re-runs `PostgresUserRepository(conn).find_by_username()` — logic the service already performs. Belt-and-braces is fine for defence in depth, but this is pure duplication; a change to the uniqueness rule requires edits in two places.

#### SoC-M2. Permission checks scattered across layers
**Files:**
- `app/matching/application/match_app_service.py:73-81, 122-126` — `is_parent/is_tutor/is_admin` checks inside the service.
- `app/teaching/api/session_router.py:40-42` — role gating in the router.
- `app/analytics/api/router.py:78-81` — role gating in the router.
- `app/messaging/api/router.py:38` — participant check in the router.

A single authorisation concept (role gating) is expressed three different ways. `require_role(...)` already exists as a FastAPI dependency; use it consistently, and keep *resource-ownership* checks (e.g., "is this the parent who owns this match") in the service.

#### SoC-M3. No application service in front of analytics / messaging repositories
**Files:** `tutor-platform-api/app/analytics/api/router.py`, `app/messaging/api/router.py`
**Evidence:** Both routers instantiate the Postgres repository (`PostgresStatsRepository`, `PostgresMessageRepository`) and call its methods directly, then post-process the result (e.g., `analytics/api/router.py:38-47` coerces breakdown rows to `float`). If income-calculation rules ever change (discounts, refunds), the logic has no obvious home.

#### SoC-M4. Admin router imports infrastructure utilities directly
**File:** `tutor-platform-api/app/admin/api/router.py:14`
**Evidence:**
```python
from app.shared.infrastructure.base_repository import (
    BaseRepository, coerce_csv_value, quote_columns, validate_columns,
)
```
Utility functions `coerce_csv_value`, `quote_columns`, `validate_columns` live in `base_repository.py` but are used by the router, not by repositories. They should live in `app/admin/infrastructure/csv_utils.py` (or similar) so the base repository module is cohesive.

#### SoC-M5. Cross-BC shared-exception coupling is inconsistent
**Files:** `app/matching/api/router.py:1-9`, `app/review/api/router.py:1-12`
**Evidence:** Some BCs import from `app.shared.domain.exceptions`, others define their own (`app/matching/domain/exceptions.py`). Each BC should own its exceptions; `shared` should only carry truly cross-cutting ones (`NotFoundError`, `PermissionDeniedError`). Today the split is incidental.

#### SoC-M6. Frontend axios interceptor mixes HTTP transport with store and routing
**File:** `tutor-platform-web/src/api/index.js:24-114`
**Evidence:** The response interceptor reads from the Pinia auth store, calls `auth.setAuth()` / `auth.logout()`, and issues `window.location = '/login'` redirects — all inside one transport module. Refresh-token queuing (lines 59-75) is hand-rolled.
**Impact:** Testing HTTP-client behaviour requires mocking Pinia + the DOM. An auth-strategy change forces a rewrite of the transport layer.

### Minor

#### SoC-m1. Duplicate float coercion in analytics router
`app/analytics/api/router.py:38-47` (income) and `:62-68` (expense) are nearly identical loops. Extract a helper in the application layer.

#### SoC-m2. `BaseRepository` is a grab-bag
`app/shared/infrastructure/base_repository.py` mixes a generic CRUD helper, CSV coercers, and column validators. Violates single-responsibility; see SoC-M4.

---

## Part 2 — Technical debt

### Critical

#### TD-C1. DDD migration is stuck at ~70%
**Directories still present:** `app/routers/`, `app/repositories/`, `app/models/` (12 + 11 + 11 files).
**Re-export shims:** `app/config.py`, `app/database.py`, `app/database_tx.py`, `app/dependencies.py`, `app/exceptions.py` — each carries the comment `# 過渡用 re-export shim — Phase 9 刪除`. Phase 9 has not happened.
**Root cause:** The test suite in `tests/conftest.py:14` imports `from app.database import get_db` (the shim) and all four test files patch `app.routers.*` symbols.
**Effort to close:** ~1-2 days. Rewrite `tests/test_matches.py`, `test_reviews.py`, `test_sessions.py`, `test_auth.py` to patch the new `app/<bc>/infrastructure/*_repo.py` classes instead; then `rm -r app/routers app/repositories app/models` plus the five shims.

#### TD-C2. Zero test coverage on the code path in production
**Covered:** only the four deprecated modules in `app/routers/`.
**Not covered:**
- `app/matching/application/match_app_service.py` (state machine orchestration — the riskiest file in the repo)
- `app/matching/domain/state_machine.py`
- `app/identity/application/services.py`, `app/identity/infrastructure/postgres_user_repo.py`
- `app/catalog/*`, `app/review/*`, `app/teaching/*`, `app/messaging/*`, `app/analytics/*`, `app/admin/*`
- All new Pydantic schemas.

**Risk:** Any regression in the shipping code lands silently. This is the single highest-leverage item in this document — fixing it simultaneously resolves TD-C1 and validates the DDD refactor.

#### TD-C3. Security-sensitive defaults live in code
**File:** `app/shared/infrastructure/config.py:7-18`
```python
database_url: str = "postgresql://tmrp:tmrp@localhost:5432/tmrp"
jwt_secret_key: str = "change-me-in-production"
admin_password: str = "admin123"
```
**Mitigation in place:** The `@model_validator` at lines 37-48 raises if the placeholder `jwt_secret_key` or `admin_password` is used. So production won't boot with them — good.
**Residual risk:** The strings are still committed to the repo, so they show up in `git grep`, SBOM scans, and IDE autocomplete. Secret-scanning tools will flag them. Replace defaults with `...` (required) or an env-only `Field(...)` so `Settings()` without `.env` fails at construction.

#### TD-C4. Shim modules block cleanup
**Files:** `app/config.py`, `app/database.py`, `app/database_tx.py`, `app/dependencies.py`, `app/exceptions.py`
Each is a one-line `from ... import * # noqa: F401`. They only exist so legacy imports keep working. Removing them is blocked on TD-C1/C2.

### Moderate

#### TD-M1. Magic numbers duplicated across layers
| Value | Locations |
|-------|-----------|
| Max students per tutor = 5 | `app/catalog/domain/entities.py:13` default; `app/catalog/infrastructure/catalog_query_adapter.py:38` fallback |
| Review lock = 7 days | `config.py:21` setting; also referenced implicitly in README and frontend copy |
| Page size = 20 | `tutor-platform-web/src/views/parent/SearchView.vue:67`; also hard-coded in some API defaults |
| Rate limits `(5, 60)` | `app/middleware/rate_limit.py:14-17` |
| JWT expiry = 15 min | `config.py:14` |
| Max upload = 50 MB, max rows = 50_000 | `app/admin/api/router.py:20-21` |

**Fix:** Pull domain constants into `app/<bc>/domain/constants.py`; keep infra knobs (rate limit, expiry, upload cap) in `settings`. Frontend should read `PAGE_SIZE` from a single `src/constants.js`.

#### TD-M2. Repositories return raw dicts; mapping happens at the top
**Files:** `app/catalog/infrastructure/postgres_tutor_repo.py` (all `fetch_*` methods), plus all of `app/*/infrastructure/postgres_*_repo.py` follow the same pattern. Routers do coercions like `round(float(t.get("avg_rating") or 0), 2)` (`tutor_router.py:61`). The domain/DTO boundary is effectively not enforced.

#### TD-M3. Hand-written DI in every router
**Pattern:** every new BC router defines a module-local `_build_service(conn)` / `_build_repo(conn)` (e.g., `tutor_router.py:13-18`, `matching/api/router.py:13-18`). This defeats FastAPI's `Depends` system, which was designed exactly for this.
**Fix:** Promote each factory to a `Depends`-returning callable in `app/<bc>/api/dependencies.py`, then routes read `service: MatchAppService = Depends(get_match_service)`.

#### TD-M4. No pagination on message retrieval
**File:** `app/messaging/api/router.py:34-41`
`get_messages(conversation_id)` returns every row. Fine for a class project, but mark as known-debt — any demo with >1k messages will hang the browser.

#### TD-M5. Complex SQL for aggregations is inlined, not viewed
**Files:** `app/catalog/infrastructure/postgres_tutor_repo.py:87-149` (`search_with_stats`), plus similar subqueries in `analytics/infrastructure/postgres_stats_repo.py`. The same `AVG(r.rating)` / `COUNT(r.review_id)` patterns recur. Candidate PostgreSQL views: `v_tutor_ratings`, `v_tutor_active_students`.

#### TD-M6. Chinese error strings in the shipping API
**Files:**
- `app/main.py:52` `"輸入資料格式錯誤"`
- `app/main.py:72` `"伺服器內部錯誤"`
- `app/main.py:61` `"HTTP 錯誤"`
- `app/admin/api/router.py:37, 64, 256, 261, 269, …` similar.

The team convention recorded in memory is *code comments English, user-facing text may be localised*. Error strings are user-facing, so this is probably fine by convention — **but** there is no i18n layer. If the project ever adds English support, every `raise DomainException("...")` must change. Worth documenting as a conscious decision rather than accidental debt.

#### TD-M7. No audit log for admin actions
**File:** `app/admin/api/router.py`
`logger.warning("Admin user_id=%s 匯入 CSV 至 %s", ...)` is the only trail for destructive operations (reset, import-all). For a rating platform, even a class project, this should write to a real `audit_logs` table — not just the log file — so actions are reviewable after rotation. Low urgency; call it out before grading if the spec mentions audit.

#### TD-M8. Inconsistent empty-string / null handling
- `app/identity/api/schemas.py:15-22` converts `""` to `None` via a Pydantic validator.
- `app/teaching/api/session_router.py:62-66` does it inline.
- `app/messaging/api/router.py:47` does a `.strip()` validation.

Three strategies for the same concept. Pick one Pydantic validator and apply at the schema layer.

### Minor

#### TD-m1. `.sixth/` is abandoned
The directory contains only an empty `skills/` folder. Nothing in the repo references it. Safe to delete; worth confirming with the team first in case someone's mid-experiment.

#### TD-m2. `ALLOWED_TABLES` is a hand-kept set
`app/admin/api/router.py:49-53`. When schema changes, this set must change too. Generate it from `information_schema.tables` at startup, or from the list of repositories.

#### TD-m3. `PostgresSessionRepository.ALLOWED_COLUMNS` referenced from router
`app/teaching/api/session_router.py:70` relies on a class-level constant existing on the repo. Runtime-only coupling. Consider a `validate_update_fields()` method on the repo itself.

#### TD-m4. Frontend has no shared API client types
`tutor-platform-web/src/views/**/*.vue` call `tutorsApi.search(params)` etc., but since the backend doesn't emit an OpenAPI schema with response models (see SoC-M3, TD-M2 — the responses aren't typed DTOs anyway), the frontend cannot autogenerate types. Adding Pydantic response models (SoC-C6) unblocks this too.

#### TD-m5. Pinia auth store lacks state-transition validation
`src/stores/auth.js` accepts any role string via `setAuth()`. A `role not in ['parent','tutor','admin']` check would catch interceptor bugs earlier.

#### TD-m6. `analytics` router duplicates coercion loops
See SoC-m1.

#### TD-m7. CSV import has no FK pre-validation
`app/admin/api/router.py:123-130`: a bad `subject_id` fails inside `cursor.execute` with the raw psycopg error. Acceptable for an admin-only endpoint; would be unacceptable if exposed to students.

---

## Part 3 — What's clean (so we don't over-correct)

It's worth calling out areas where the codebase already does the right thing, so fixes don't accidentally regress them:

- **Middleware stack** (`app/main.py:138-154`) is correctly ordered with explanatory comments on why: CORS outermost, rate-limit innermost. The comment at line 138 explains the Starlette registration-order inversion — that's load-bearing documentation, do not remove.
- **Exception handlers** (`app/main.py:38-76`) are cleanly centralised; `DomainException` is the single shape the HTTP layer maps.
- **Match state machine** (`app/matching/domain/state_machine.py`) is properly isolated in the domain layer — no HTTP or DB types leak in.
- **Lifespan** (`app/main.py:84-111`) correctly blocks startup on DB schema init (see the Bug #17 comment), and closes the pool on shutdown.
- **Pydantic schemas** exist per BC under `app/<bc>/api/schemas.py` — the DTO pattern is set up; it just isn't used for *responses* yet (see SoC-C6).
- **RequestID middleware** is wired into error responses (`app/main.py:67-75`), which is the right pattern for operability.

---

## Part 4 — Recommendations (priority order)

Each item lists the **unlock** it creates, so the sequence is deliberate.

1. **Migrate the test suite off legacy routers** (TD-C2).
   *Rewrite `tests/test_{auth,matches,reviews,sessions}.py` to patch `app/<bc>/infrastructure/*_repo.py` and exercise the new routers.*
   Unlocks: TD-C1, TD-C4.

2. **Delete the legacy layer** (TD-C1, TD-C4).
   `rm -r app/routers app/repositories app/models`; delete the five shim modules. Run the test suite.
   Unlocks: clean module map; removes the `DeprecationWarning` noise.

3. **Introduce response DTOs** (SoC-C6, TD-M2).
   Add `app/<bc>/api/schemas.py::*Response` Pydantic models; make services return domain objects, routers map to DTOs. This incidentally gives the frontend typed clients (TD-m4).

4. **Move router-side logic into domain/application services** (SoC-C3, SoC-C4, SoC-C5, SoC-M3).
   Start with `admin/api/router.py` (the worst offender); then dedupe `apply_visibility` in `catalog/`.

5. **Replace `_build_service(conn)` helpers with `Depends()` factories** (TD-M3).
   One file per BC under `app/<bc>/api/dependencies.py`.

6. **Consolidate constants** (TD-M1).
   Domain constants → `app/<bc>/domain/constants.py`; infra → `settings`. Delete duplicated fallbacks.

7. **Remove `conn` from application service constructors; introduce a `UnitOfWork` port** (SoC-C2).
   Biggest architectural improvement; do it after DTOs so the blast radius is controlled.

8. **Harden secret defaults** (TD-C3).
   `jwt_secret_key: str = Field(...)` (required) and remove the placeholder strings.

9. **Centralise permission checks** (SoC-M2).
   Standardise on `require_role(...)` for role-gating; keep resource-ownership in services.

10. **Add pagination to messaging; add audit-log table for admin actions** (TD-M4, TD-M7). Pure adds, no refactor risk.

11. **Delete `.sixth/`** (TD-m1) after confirming with the team.

---

## Appendix A — File-by-file hotspots

| File | Concern | Lines |
|------|---------|-------|
| `app/main.py` | Chinese error strings (TD-M6) | 52, 61, 72 |
| `app/matching/application/match_app_service.py` | Service holds `conn` (SoC-C2) | 22, 25, 32, 150 |
| `app/matching/application/match_app_service.py` | Entity→response hand-mapping (SoC-C6) | 84-112 |
| `app/admin/api/router.py` | Raw SQL in routes (SoC-C3) | 121-130, 162-178, 274-315 |
| `app/admin/api/router.py` | Imports infra utils (SoC-M4) | 14 |
| `app/admin/api/router.py` | Hard-coded table list (TD-m2) | 49-53 |
| `app/catalog/api/tutor_router.py` | Visibility masked in router + service (SoC-C4) | 54-64, 136-142 |
| `app/catalog/api/tutor_router.py` | Function-local infra import (SoC-C5) | 89-95 |
| `app/identity/api/router.py` | Duplicate username check (SoC-M1) | 33-36 |
| `app/analytics/api/router.py` | No service layer (SoC-M3); dup coercion (SoC-m1) | 38-47, 62-68 |
| `app/messaging/api/router.py` | No service layer; no pagination (SoC-M3, TD-M4) | 13-53, 34-41 |
| `app/shared/infrastructure/config.py` | Secret defaults (TD-C3) | 7-18 |
| `app/shared/infrastructure/base_repository.py` | Grab-bag module (SoC-m2) | — |
| `app/routers/__init__.py` | Deprecated layer (TD-C1) | 2-32 |
| `app/{config,database,database_tx,dependencies,exceptions}.py` | Shim modules (TD-C4) | all |
| `tests/conftest.py` | Imports shim (TD-C1) | 14 |
| `tests/test_matches.py` | Patches legacy (TD-C2) | 38-40 |
| `tutor-platform-web/src/api/index.js` | Interceptor couples transport+store+routing (SoC-M6) | 24-114 |
| `tutor-platform-web/src/views/parent/SearchView.vue` | Hard-coded page size (TD-M1) | 67 |
| `.sixth/` | Abandoned directory (TD-m1) | — |

---

## Appendix B — Issue taxonomy

- **SoC-C1 … SoC-C6**: Critical separation-of-concerns violations (6).
- **SoC-M1 … SoC-M6**: Moderate SoC issues (6).
- **SoC-m1, SoC-m2**: Minor SoC issues (2).
- **TD-C1 … TD-C4**: Critical technical debt (4).
- **TD-M1 … TD-M8**: Moderate technical debt (8).
- **TD-m1 … TD-m7**: Minor technical debt (7).

**Total:** 33 items. The three that matter most are TD-C1, TD-C2, SoC-C6 — landing those simultaneously (they share a fix) would move the project from "DDD-shaped" to "DDD-grade".

---

## Appendix C — Resolution status (2026-04-12)

Moderate and minor items addressed in this pass:

| Item | Status | Resolution |
|------|--------|------------|
| TD-M1 | Fixed | `DEFAULT_MAX_STUDENTS_PER_TUTOR` in `app/catalog/domain/constants.py`; `DEFAULT_PAGE_SIZE` / `MAX_PAGE_SIZE` in `app/shared/api/constants.py`; upload caps in `Settings`; `tutor-platform-web/src/constants.js` for `PAGE_SIZE`. |
| TD-M3 | Fixed | `app/<bc>/api/dependencies.py` modules added; routers now take `service: X = Depends(get_x_service)`. |
| TD-M4 | Fixed | `GET /api/messages/conversations/{id}` accepts `limit` (≤500) and cursor `before_id`; repo uses id-desc + reverse. |
| TD-M5 | Fixed | Views `v_tutor_ratings` and `v_tutor_active_students` added to `init_db.py`; tutor repo and catalog adapter use them. |
| TD-M8 | Fixed | Shared `OptionalStr` / `TrimmedStr` in `app/shared/api/validators.py`; adopted in identity, messaging, and catalog schemas. |
| TD-m1 | Fixed | `.sixth/` deleted. |
| TD-m2 | Fixed | `ALLOWED_TABLES = frozenset(DELETE_ORDER)`; one source of truth. |
| TD-m3 | Fixed | `PostgresSessionRepository.validate_update_fields()`; `ALLOWED_COLUMNS` renamed `_ALLOWED_UPDATE_COLUMNS` (private). |
| TD-m5 | Fixed | `setAuth()` rejects `userData` whose `role` is not in `['parent','tutor','admin']`. |
| TD-m7 | Fixed | `_format_row_error()` in admin import service turns psycopg FK / unique / not-null errors into readable admin-UI messages. |

Knowingly accepted (no change; documented rationale):

| Item | Status | Rationale |
|------|--------|-----------|
| TD-M2 | Accepted | DTO boundary overlaps with SoC-C6. Will be resolved as part of the response-DTO rollout (Part 4, step 3), not piecemeal here. |
| TD-M6 | Accepted | Team convention: user-facing copy may be localised. No i18n layer planned for the course project. Will revisit if English support is ever added. |
| TD-M7 | Accepted | Structured `audit_logs` table is out of scope for the course project; current `logger.warning(...)` trails plus rate-limit caps on destructive endpoints are sufficient for the grading rubric. |
| TD-m4 | Accepted | Blocked on SoC-C6 / TD-M2 (needs typed response DTOs before OpenAPI client generation is meaningful). |
| TD-m6 | Accepted | Will be resolved together with SoC-m1 when analytics gets its response DTOs. |

