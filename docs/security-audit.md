# TMRP Security Audit Report

**Project:** Tutor Matching and Rating Platform
**Audit date:** 2026-04-17
**Scope:** Full-stack review of `tutor-platform-api` (FastAPI + PostgreSQL), `tutor-platform-web` (Vue 3 SPA + nginx), `docker-compose.yml`, `secrets/`, and dependency manifests.
**Method:** Four parallel specialist audit passes — (1) backend API, (2) frontend web, (3) infrastructure/deployment, (4) business logic & data exposure — followed by cross-consolidation and deduplication.

---

## 1. Executive Summary

The codebase is materially more hardened than a typical student or early-stage project. Positive observations:

- SQL is parameterised everywhere via `psycopg2.sql.Identifier`/`Placeholder`; no string-concatenated SQL found.
- JWT uses HS256 with ≥32-char secret enforcement, `type` claim validation, DB-backed refresh-token JTI blacklist, key rotation, and placeholder-secret rejection at boot.
- Passwords use bcrypt with constant-time duplicate-user handling to defeat enumeration.
- Frontend has a build-time guard against `v-html` / `innerHTML` and a full CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, and Permissions-Policy stack in nginx.
- Tokens live in HttpOnly cookies (not `localStorage`).
- Mass-assignment protection via explicit column whitelists (`PROFILE_COLUMNS`, `VISIBILITY_COLUMNS`, `ALLOWED_COLUMNS`, `Literal["parent","tutor"]` on registration role).
- Admin reset flow is two-step with tight rate limits and pre-reset auto-backup.

### Severity distribution

| Severity | Count |
|----------|-------|
| Critical | 1 |
| High     | 5 |
| Medium   | 12 |
| Low      | 8 |
| Info     | 4 |
| **Total**| **30** |

### Top three priorities

1. **CRITICAL-1** — Purge historical JWT secret + admin password from git history, rotate credentials.
2. **HIGH-1 / HIGH-2** — Stop leaking tutor `email` + `phone` from public catalog endpoint; stop writing plaintext passwords to `app.log` via Pydantic validation handler.
3. **HIGH-3** — Add CSRF defense (non-simple header or double-submit token) to the cookie-authenticated SPA.

---

## 2. Critical Findings

### CRITICAL-1 — JWT secret and admin password leaked in git history
- **Category:** Secrets management
- **Location:** `tutor-platform-api/.env.docker` (current working file); historical blobs in commits `cb7ad86` and `950a53e`
- **Evidence:** `git log -S "JWT_SECRET_KEY=" -- '*.env*'` returns two commits exposing the secret. The file's own header comment (`.env.docker:8, 19-21`) acknowledges the prior leak of `JWT_SECRET_KEY` and `ADMIN_PASSWORD=<REDACTED>`.
- **Description:** A real 256-bit HS256 secret plus the bootstrap admin password were committed to the repo. `.env.*` is now gitignored, but history was never rewritten, so anyone with read access to the repo (or to clones/forks made before remediation) retains the leaked secrets.
- **Impact:** An attacker can forge arbitrary JWTs for any user or role, including admin. If the admin password was reused elsewhere, that reuse is also exposed.
- **Recommendation:**
  1. Rewrite history with `git filter-repo` / BFG to remove every `.env*` blob, then force-push. Notify all clone-holders.
  2. After purge, rotate `JWT_SECRET_KEY` again and rotate `ADMIN_PASSWORD` in the live DB.
  3. Move live secrets to Docker secrets (same pattern already used by `db_password`) rather than env files next to a `.example` sibling.
- **Status (2026-04-17):** Steps 2 and 3 applied in this commit — `JWT_SECRET_KEY`, `JWT_SECRET_KEY_PREVIOUS`, and `ADMIN_PASSWORD` are now Docker secrets under `./secrets/`, loaded into the container via `tutor-platform-api/docker-entrypoint.sh`; `.env.docker` no longer carries them. **Step 1 (history rewrite) is outstanding** — the leaked values in commits `cb7ad86` and `950a53e` remain valid against any clone or fork made before the rewrite, so rotation alone is insufficient. Runbook below.

#### History-rewrite runbook (coordinate with the team before running)

Pre-flight:
- Announce a freeze window on `main`; every team member pushes outstanding work first.
- Confirm no open PRs depend on the to-be-rewritten commits (they will need to be rebased afterwards).
- Take a safety mirror: `git clone --mirror <origin> tmrp-premigration.git` and archive it offline.

Rewrite (using [`git-filter-repo`](https://github.com/newren/git-filter-repo), preferred over BFG for path globs):

```bash
git clone --mirror git@github.com:TMRP-NTNU-2026-SQL-Group-3/TMRP-Tutor-Matching-and-Rating-Platform-.git tmrp.git
cd tmrp.git
git filter-repo --invert-paths \
  --path-glob 'tutor-platform-api/.env.docker' \
  --path-glob 'tutor-platform-api/.env' \
  --path-glob '.env'
# Verify the leaked strings are gone from every reachable blob:
git log -S 'JWT_SECRET_KEY=' --all --oneline            # expect empty
git log -S '<REDACTED>' --all --oneline             # expect empty
git push --force --all
git push --force --tags
```

Post-rewrite:
- Every contributor must re-clone (or `git fetch && git reset --hard origin/<branch>` on a fresh checkout). Stale local clones still contain the leaked blobs.
- Rotate `JWT_SECRET_KEY` and `ADMIN_PASSWORD` **again** (the first rotation sat in a working tree that touched the pre-rewrite remote): regenerate `secrets/jwt_secret_key.txt` and `secrets/admin_password.txt`, then update the `admin` row: `UPDATE users SET password_hash = <bcrypt(NEW_PWD)> WHERE username = 'admin';`
- If a rotation window is needed, move the old key into `secrets/jwt_secret_key_previous.txt` for `2 × JWT_EXPIRE_MINUTES`, then clear it.
- Revoke any GitHub forks that existed before the rewrite (GitHub retains fork blobs independently — contact GitHub Support to purge if the forks are not under your control).

---

## 3. High Findings

### HIGH-1 — PII disclosure: tutor `email` and `phone` exposed to every authenticated user
- **Category:** Business logic / data exposure
- **Location:** `tutor-platform-api/app/catalog/infrastructure/postgres_tutor_repo.py:164-170` (query), `app/catalog/domain/services.py:15-40` (`apply_visibility`), `app/catalog/api/tutor_router.py:131-147` (route)
- **Description:** `find_by_id` selects `t.*, u.display_name, u.email, u.phone`. `apply_visibility` only strips `university`, `department`, `grade_year`, `active_student_count`, `subjects`, and `show_*` flags. `email` and `phone` remain in every response. There is no tutor-controlled `show_email`/`show_phone` flag.
- **Impact:** Any logged-in user can enumerate `GET /api/tutors/{id}` and harvest every tutor's email and phone. Mass spam / phishing / off-platform poaching (which directly undermines the platform's matching economics) and likely PDPA/GDPR exposure.
- **Recommendation:** In `apply_visibility`, `tutor.pop("email", None); tutor.pop("phone", None)`. Expose contact info only once a match reaches `active`/`trial`, or via `/api/auth/me` for the tutor's own record.

### HIGH-2 — Plaintext passwords and refresh tokens written to application log
- **Category:** Logging / data exposure
- **Location:** `tutor-platform-api/app/main.py:47-48` (`validation_exception_handler`)
- **Description:** The handler logs `exc.errors()` verbatim. Pydantic's error dicts include the raw `input` field. Confirmed in `logs/app.log:1042,1048` — entries like `'input': 'pass'` for `body.password`. Failed registration/login/refresh validation persists the candidate credential in plaintext. Compounds with HIGH-5 (body-fallback refresh) — a malformed refresh body writes a live 7-day refresh token to the log.
- **Impact:** Any party with log-read access (ops, backup stores, leaked container volume) can recover real passwords and refresh tokens. Violates OWASP ASVS V7.1.1.
- **Recommendation:** Before logging, redact the `input` key for any error whose `loc` path contains `password`, `refresh_token`, `reset_token`, or `authorization`. Simpler: drop the `input` key entirely and log only `{loc, type, msg}`.

### HIGH-3 — No CSRF defense on cookie-authenticated SPA
- **Category:** Frontend / auth
- **Location:** `tutor-platform-web/src/api/index.js:11-16` (axios `withCredentials: true`); absence of CSRF-header or double-submit logic anywhere in `src/api/*` and `src/stores/auth.js:63`
- **Description:** Auth cookies are HttpOnly and attached automatically by the browser. No `X-CSRF-TOKEN` / `X-XSRF-TOKEN` header, no forced-preflight custom header, no double-submit token. Cookie `SameSite` attribute is not asserted client-side.
- **Impact:** If the backend cookie is not strictly `SameSite=Strict` (or if an attacker-controlled subdomain exists), any attacker origin can trigger state-changing requests including `POST /api/matches`, admin actions, or `/api/auth/logout` (DoS).
- **Recommendation:** Add an axios request interceptor that attaches a non-simple header on all mutating methods (`config.headers['X-Requested-With'] = 'XMLHttpRequest'`) to force CORS preflight, OR implement double-submit (readable `XSRF-TOKEN` cookie → mirrored `X-XSRF-TOKEN` header). Verify backend sets `SameSite=Strict` on the auth cookie.

### HIGH-4 — Weak-placeholder DB password in committed example file
- **Category:** Secrets / ops
- **Location:** `secrets/db_password.txt.example:1`
- **Description:** Content is the literal `please_change_me_to_a_strong_random_password`. `.gitignore` rule `!secrets/*.example` keeps this file tracked. One `cp db_password.txt.example db_password.txt` away from shipping the placeholder to production.
- **Impact:** Trivially guessable DB password if the example is ever deployed unedited.
- **Recommendation:** Ship an empty `.example` with inline instructions, and add a boot-time check in `docker-entrypoint.sh` that rejects any known-placeholder string.

### HIGH-5 — Postgres container lacks hardening directives; port published to host
- **Category:** Container / infrastructure
- **Location:** `docker-compose.yml:7-34`
- **Description:** The `db` service does not set `user:`, no `security_opt: ["no-new-privileges:true"]`, no `cap_drop: [ALL]`, no `read_only: true`. Port `127.0.0.1:5432:5432` is bound to loopback — acceptable for dev, but the same compose file is the only one in the repo (no `docker-compose.prod.yml` override). The inline comment already admits "in prod this whole `ports:` block should be removed".
- **Impact:** Container-escape CVEs gain excess capability; any local process on a multi-tenant host can hit the DB; SSH port-forwarding silently exposes it.
- **Recommendation:** Add to every service in compose: `security_opt: ["no-new-privileges:true"]`, `cap_drop: ["ALL"]`, `read_only: true` (with explicit `tmpfs` for writable paths). Add `user: "70:70"` to `db`. Move the `ports:` block to a dev-only `docker-compose.override.yml`.

---

## 4. Medium Findings

### MEDIUM-1 — Body-size cap bypassable via chunked transfer encoding
- **Location:** `tutor-platform-api/app/middleware/body_size_limit.py:23-44`
- **Description:** The middleware only inspects `Content-Length`. HTTP/1.1 clients sending `Transfer-Encoding: chunked` send no `Content-Length`, so `cl is None` and the check is skipped.
- **Impact:** DoS via unbounded upload on any endpoint; defeats the stated 50 MB cap.
- **Recommendation:** Stream-count bytes as the body is read (wrap `request.stream()`), and add a hard cap at the uvicorn/nginx layer for defence in depth.

### MEDIUM-2 — Rate limiting keys off socket peer IP, not real client IP
- **Location:** `tutor-platform-api/app/middleware/rate_limit.py:176` (`ip = request.client.host`)
- **Description:** Uvicorn is not started with `--proxy-headers`, and no `X-Forwarded-For` parsing exists. Behind the nginx container (as the repo is configured), every request appears from the proxy IP → one shared bucket.
- **Impact:** Legitimate users collectively hit the 60/min ceiling; per-IP brute-force defense is neutered.
- **Recommendation:** `uvicorn --proxy-headers --forwarded-allow-ips=<nginx-net>`, and use the parsed IP for `bucket_key`.

### MEDIUM-3 — Nginx forwards client-supplied `X-Forwarded-For` without trust gating
- **Location:** `tutor-platform-web/nginx.conf:60` (`proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`)
- **Description:** `$proxy_add_x_forwarded_for` appends whatever the client sent. Once MEDIUM-2 is fixed and the backend trusts XFF, the attacker can still spoof arbitrary IPs through the frontend nginx.
- **Impact:** Rate-limit bypass; log poisoning.
- **Recommendation:** Replace with `proxy_set_header X-Forwarded-For $remote_addr;` (single trusted hop) OR add `set_real_ip_from <trusted proxy CIDR>; real_ip_header X-Forwarded-For;`.

### MEDIUM-4 — Client-side role trust (`user.role` from `localStorage`)
- **Location:** `tutor-platform-web/src/stores/auth.js:20` (`JSON.parse(localStorage.getItem('user'))`), `src/router/index.js:86-114`
- **Description:** Pinia seeds `user.role` from `localStorage`, and route guards trust it. An XSS primitive or browser extension can set `localStorage.user = {role:"admin",...}` and render admin UI. Backend still 403s API calls, but the admin layout structure and any cached/optimistic content leak.
- **Impact:** Client-side privilege escalation; reconnaissance of admin UI; amplifies any future server-side authorization bug.
- **Recommendation:** On app boot, `await /api/auth/me` inside an async router guard and treat `localStorage.user` as cache only. Never authorize views from client-held role strings.

### MEDIUM-5 — `/api/auth/refresh` and `/api/auth/logout` accept tokens from request body
- **Location:** `tutor-platform-api/app/identity/api/router.py:108-125, 137-139`
- **Description:** A "backward compatibility" fallback reads `body.refresh_token`. This bypasses the SameSite protection of the HttpOnly cookie and makes stolen tokens replayable from any origin that can POST JSON.
- **Impact:** Undermines the security rationale of moving to HttpOnly cookies; compounds HIGH-2's log-leak path.
- **Recommendation:** Remove the body fallback now that the SPA uses cookies. If kept, require a matching CSRF header.

### MEDIUM-6 — Conversation creation enumerates arbitrary user IDs
- **Location:** `tutor-platform-api/app/messaging/application/message_service.py:25-33`
- **Description:** `create_conversation` raises `TargetUserNotFoundError` for missing IDs but silently succeeds for any valid ID, regardless of any prior match/relationship.
- **Impact:** (a) User-ID enumeration via 404/200 oracle; (b) unsolicited DM to any registered user — spam/harassment, especially concerning given the student population may include minors.
- **Recommendation:** Require at least one non-rejected match between the two users before allowing conversation creation. Return an identical generic response for both "no such user" and "not matched" to prevent enumeration.

### MEDIUM-7 — Student-progress endpoint reveals existence of arbitrary student IDs
- **Location:** `tutor-platform-api/app/analytics/application/stats_service.py:73-81`
- **Description:** `student_progress` calls `get_student(student_id)` and raises `NotFoundError` before the ownership check. Unauthorized callers distinguish "does not exist" (404) from "not yours" (403).
- **Impact:** IDOR-adjacent enumeration of the student table; facilitates targeted harassment in combination with MEDIUM-6.
- **Recommendation:** Collapse both paths to a single "not found or not permitted" 404.

### MEDIUM-8 — Tutor reviews endpoint unpaginated, exposes private fields
- **Location:** `tutor-platform-api/app/catalog/api/tutor_router.py:150-163`
- **Description:** `GET /api/tutors/{id}/reviews` returns `r.*` including `personality_comment` (the tutor's private note about the parent), `reviewer_user_id`, and unbounded rows.
- **Impact:** Parent identity graph reconstructable across tutors; private notes leak; DoS on high-rated tutors.
- **Recommendation:** Project only public columns (`rating_*`, `comment`, `created_at`, anonymised reviewer label), add `LIMIT`/`OFFSET`.

### MEDIUM-9 — Review schema allows unjustified low-score griefing
- **Location:** `tutor-platform-api/app/review/api/schemas.py:4-21`
- **Description:** `tutor_to_parent` / `tutor_to_student` allow null `rating_3`/`rating_4`. Any `rating_*` can be `1` with optional comment. A retaliatory 1-star review needs no justification.
- **Impact:** Reputation griefing; skews any future aggregate on the tutor-side review axes.
- **Recommendation:** Require `comment` (min 10 chars) whenever any rating ≤ 2; require all-or-none for `tutor_to_*` rating axes.

### MEDIUM-10 — Base images not digest-pinned
- **Location:** `tutor-platform-api/Dockerfile:1` (`python:3.12-slim`), `tutor-platform-web/Dockerfile:2, 22` (`node:20-alpine`, `nginxinc/nginx-unprivileged:alpine`), `docker-compose.yml:8` (`postgres:16-alpine`)
- **Description:** No `@sha256:...` pins; floating tags pull different layer sets on every rebuild.
- **Impact:** Non-reproducible builds; supply-chain pushes (compromised upstream, typosquat) land silently.
- **Recommendation:** Pin each base image by digest; automate digest updates via Renovate/Dependabot.

### MEDIUM-11 — `psycopg2-binary==2.9.10` bundles libpq vulnerable to CVE-2024-10977
- **Location:** `tutor-platform-api/requirements.txt:5`
- **Description:** libpq <17.1 (bundled by 2.9.10) allows error-message spoofing during TLS negotiation. Impact is bounded today because the DB is reached over an untrusted-free compose bridge, but any move to managed Postgres with TLS makes this exploitable.
- **Recommendation:** Upgrade to `psycopg2-binary>=2.9.11`, or migrate to `psycopg[binary]>=3.2.3`.

### MEDIUM-12 — HSTS emitted on plain-HTTP listener; no in-container TLS assumption documented
- **Location:** `tutor-platform-web/nginx.conf:14,32`
- **Description:** nginx listens on plain HTTP (port 8080) and emits `Strict-Transport-Security` unconditionally. If fronted without a TLS-terminating proxy, HSTS is ignored and all traffic including JWT cookies flows cleartext.
- **Recommendation:** Document TLS-terminating proxy (Caddy / Traefik / ALB) as a hard deployment prerequisite in README; add a startup guard or split configs so the container refuses to serve plain HTTP in prod.

---

## 5. Low Findings

### LOW-1 — CORS `allow_origins` parsed from comma-split env with no validation
- **Location:** `tutor-platform-api/app/main.py:191-200`, `app/shared/infrastructure/config.py:51`
- **Description:** `settings.cors_origins` is a raw string. No check for `"*"` or scheme correctness. With `allow_credentials=True`, a misconfigured env would silently trust an arbitrary origin. Operational foot-gun.
- **Recommendation:** In `Settings`, validate each entry is `https://...` in non-debug mode and reject `*`.

### LOW-2 — Login audit log ingests raw attacker-supplied username
- **Location:** `tutor-platform-api/app/identity/domain/services.py:68-72`; schema `app/identity/api/schemas.py`
- **Description:** `login_failed username=%s` is logged with no length cap on `LoginRequest.username`. Plain-text log readers vulnerable to log forging via newline injection; disk-exhaustion via large usernames combined with MEDIUM-1.
- **Recommendation:** Add `max_length=64` + character-class validator; truncate before logging.

### LOW-3 — `/api/admin/import` single-CSV path skips `MAX_UPLOAD_SIZE` check
- **Location:** `tutor-platform-api/app/admin/api/router.py:55-67`
- **Description:** Reads `file.file.read()` in full without size check, while `import_zip` (`import_service.py:99`) does check. Combined with MEDIUM-1, an admin user can OOM the worker.
- **Recommendation:** Apply the same `len(data) > MAX_UPLOAD_SIZE` guard to CSV uploads or stream-parse.

### LOW-4 — Admin reset-confirmation token reusable within 5-minute TTL
- **Location:** `tutor-platform-api/app/admin/api/router.py:98-172`, `app/shared/infrastructure/security.py:215-243`
- **Description:** No JTI revocation after a `/reset/confirm` attempt (success or failure). The most destructive endpoint in the platform is replayable for 5 minutes.
- **Recommendation:** Store issued reset JTIs in `refresh_token_blacklist` (or a new `reset_token_used` table) and mark consumed on first attempt.

### LOW-5 — `console.error` ships error objects in production bundle
- **Location:** `tutor-platform-web/src/main.js:25,30,35`
- **Description:** Production builds retain `console.error(err)` / `event.reason` / `event.error`, leaking stack traces and backend error envelopes to anyone near the screen or any extension with devtools access.
- **Recommendation:** Gate on `import.meta.env.DEV`, or `vite.config.js`: `esbuild.drop: ['console','debugger']`. Ship real telemetry instead.

### LOW-6 — CSP retains `style-src 'unsafe-inline'`
- **Location:** `tutor-platform-web/nginx.conf:37, 90, 108`
- **Description:** Retained for Tailwind. Weakens CSP against style-based data exfiltration / CSS keylogging.
- **Recommendation:** Migrate to nonce-based `style-src`, or hash-pin the Tailwind inline-style set.

### LOW-7 — Missing Cross-Origin isolation headers
- **Location:** `tutor-platform-web/nginx.conf:20-37`
- **Description:** No `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`, or `Cross-Origin-Embedder-Policy`. Without COOP, popup opener references survive cross-origin navigation.
- **Recommendation:** Add `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Resource-Policy: same-site` to every `location` block.

### LOW-8 — API Dockerfile keeps build tools (`gcc`, `libpq-dev`) in final image
- **Location:** `tutor-platform-api/Dockerfile:6-8`
- **Description:** `psycopg2-binary` ships prebuilt wheels, so `gcc`+`libpq-dev` aren't needed at runtime. Adds attack surface and ~150 MB.
- **Recommendation:** Drop `gcc libpq-dev` (keep only `curl` for healthcheck), or move to multi-stage build.

---

## 6. Informational

### INFO-1 — Password policy: 8 chars, letters + digits only
- **Location:** `tutor-platform-api/app/identity/api/schemas.py:26-33`
- **Description:** Accepts `abcdefg1`; no symbol requirement, no breached-password check. Per-username rate limit (5/15min) makes this tolerable, but weak by 2026 norms.
- **Recommendation:** Raise to ≥10 chars or integrate a k-anonymity pwned-passwords check.

### INFO-2 — `cookie_secure` defaults to `False`
- **Location:** `tutor-platform-api/app/shared/infrastructure/config.py:55`
- **Description:** Operator must remember to set `COOKIE_SECURE=true` in prod.
- **Recommendation:** In `reject_placeholder_secrets`, require `cookie_secure=True` when `debug=False`.

### INFO-3 — `admin` is the predictable bootstrap username
- **Location:** `tutor-platform-api/.env.docker:16`, `.env.docker.example:16`
- **Recommendation:** Allow arbitrary bootstrap username; default to an enumeration-resistant form (e.g., `owner_<random6>`).

### INFO-4 — Committed `.env` overrides intended `.env.development` empty value
- **Location:** `tutor-platform-web/.env:1` vs `.env.development:3`
- **Description:** Committed `.env` sets a cross-origin dev baseURL, so `npm run dev` sends credentialed requests cross-origin to `localhost:8000` — requires permissive CORS on the API for dev. Confirm that config does not bleed to prod.
- **Recommendation:** Remove the committed `.env`; rely on `.env.development` / `.env.production` / `.env.local`. Add to `.gitignore`.

---

## 7. Verified-Safe Controls (Audit Evidence)

The following were actively tested and found correct — listing them prevents future regressions and documents the intended design.

- **SQL injection:** All dynamic SQL in `postgres_tutor_repo.py`, `table_admin_repo.py`, etc. uses `psycopg2.sql.Identifier` / `Placeholder`; `sort_by` and table names are whitelisted; LIKE inputs are passed through `escape_like`. No f-string or `.format()` SQL found.
- **JWT:** HS256; ≥32-char secret enforced; `type` claim checked on every decode; placeholder secrets rejected at boot; key rotation supported; refresh-JTI blacklist is DB-backed.
- **Password storage:** bcrypt with per-call salt; duplicate-username registration path burns an equivalent hash for timing safety.
- **Pickle / RCE:** Huey uses a custom JSON serializer; `get_task_status` refuses pickle fallback explicitly.
- **Path traversal:** ZIP import uses `zf.read(name)` (in-memory), never `extractall`. CSV export filename regex-sanitised. No user-controlled FS paths.
- **Admin reset:** Two-step flow (fresh reset token + password re-verify + pre-reset auto-backup + tight rate limits) — see LOW-4 for the one remaining gap (JTI revocation).
- **IDOR on students / sessions / reviews / matches / messages:** Every destructive or read endpoint verified to enforce ownership via `parent_user_id` / `tutor_user_id` / `user_is_participant`.
- **Mass assignment:** Update endpoints use whitelisted column sets. `RegisterRequest.role` is `Literal["parent","tutor"]` — registration as `admin` is rejected by Pydantic before hitting the service.
- **Error handling:** Unhandled exceptions return generic 500; `request_id` is in a header only, not the body.
- **Open redirect / SSRF:** No `redirect` parameter handling, no outbound HTTP calls based on user input found.
- **Self-match:** Parent and tutor are disjoint roles; `matches` joins through `students.parent_user_id` and `tutors.user_id`; a user cannot occupy both sides.
- **Self-review / duplicate review:** `create_review` enforces role-from-match; unique `(match_id, reviewer_user_id, review_type)` prevents inflation.
- **Matching race:** `create_match` and `RESUME` both `lock_tutor_for_update` before capacity check inside the same UoW.
- **Login/registration enumeration:** Identical 401 for unknown-user and bad-password; per-account rate limit applied before bcrypt regardless of existence.
- **Admin endpoints:** Every route in `app/admin/api/router.py` uses `require_role("admin")`.
- **XSS:** Zero `v-html` / `innerHTML` / `dangerouslySetInnerHTML` in `src/**`; build-time guard at `scripts/check-no-v-html.mjs:38` runs on `prebuild`.
- **Token storage (frontend):** No JWT/refresh in `localStorage`; legacy `token`/`refreshToken` keys are actively purged at `src/stores/auth.js:16-17`.
- **Clickjacking:** `X-Frame-Options: DENY` + CSP `frame-ancestors 'none'` on every `location` block.
- **Directory listing / dotfile exposure:** Blocked at `nginx.conf:70-74`.
- **Prototype pollution:** No `__proto__` / unsafe merge patterns in `src/**`.
- **Frontend dependencies:** `axios 1.7.9`, `vue 3.5.13`, `vue-router 4.5.0`, `pinia 2.3.0`, `vite 6.0.5`, `chart.js 4.5.1` — no known CVEs at these ranges as of audit cutoff.
- **`.gitignore` coverage:** `git ls-files secrets/` is empty; `git ls-files | grep env` returns only `*.example` and an empty `.env.production`. `.gitleaks.toml` and `.pre-commit-config.yaml` are in place.

---

## 8. Remediation Roadmap

### Immediate (days)
1. CRITICAL-1: git-history purge + credential rotation.
2. HIGH-2: redact `input` in validation error logs.
3. HIGH-1: strip `email`/`phone` from tutor-detail response.

### Short-term (this sprint)
4. HIGH-3: CSRF defense (custom header or double-submit).
5. HIGH-4: replace `db_password.txt.example` content + startup placeholder check.
6. HIGH-5: add `no-new-privileges`, `cap_drop: ALL`, `read_only: true` to compose; move `db` `ports:` to a dev-only override.
7. MEDIUM-1..3: body-size counting, real-IP parsing, XFF trust gating.
8. MEDIUM-5: drop refresh/logout body fallback.

### Medium-term
9. MEDIUM-4: async `/auth/me` in router boot, stop trusting `localStorage.user` for authorization.
10. MEDIUM-6,7: collapse enumeration oracles; gate conversation creation on match.
11. MEDIUM-8: paginate + project tutor-reviews response; strip `personality_comment`.
12. MEDIUM-9: tighten review validation for low ratings.
13. MEDIUM-10: digest-pin base images.
14. MEDIUM-11: upgrade `psycopg2-binary`.
15. MEDIUM-12: formalize TLS-fronting requirement.

### Hardening debt
16. All LOW and INFO items.

---

*End of report.*
