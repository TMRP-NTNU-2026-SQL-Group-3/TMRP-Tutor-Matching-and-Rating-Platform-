# Security Policy

## Scope

TMRP (Tutor Matching and Rating Platform) is an academic capstone project. Its security controls are designed to reflect production-grade intent within the constraints of a university course. This document describes what those controls are, where they have known gaps, and how to operate the system securely.

We welcome responsible disclosure and are transparent about limitations.

---

## Reporting a Vulnerability

If you discover a security issue, please open a [GitHub Issue](../../issues) marked **[SECURITY]** or contact the repository owner directly. We are a small student team and cannot offer a bug bounty, but we will acknowledge reports promptly and act on valid findings.

Please include:
- A clear description of the vulnerability and its impact
- Reproduction steps or a proof of concept
- Any relevant request/response captures (redact actual credentials)

We ask that you avoid automated scanning tools against the live demo environment, if one is deployed.

---

## Supported Versions

This is a single-version project; security fixes are applied directly to `main`. There are no LTS or stable branches.

---

## Authentication and Session Management

### JWT Lifecycle

Access tokens have a hard-capped 5-minute TTL (`JWT_EXPIRE_MINUTES`, max 10). Refresh tokens have a 7-day TTL and are stored exclusively in an `HttpOnly; SameSite=Lax; Path=/api/auth` cookie — they are never readable by JavaScript.

Both token types carry `jti` (unique identifier), `iat`, `exp`, and a `type` claim (`access` vs `refresh`). The `alg=none` algorithm is explicitly rejected before decode. Symmetric signing uses HS256; keys must be at least 32 characters and may not be placeholder values (enforced at startup).

### Refresh Token Revocation

Revoked JTIs are persisted in `refresh_token_blacklist` and checked on every refresh request. An in-memory LRU cache (1 000 entries) reduces DB round-trips. A background Huey task periodically purges expired entries.

### Key Rotation

The `JWT_SECRET_KEY_PREVIOUS` and `JWT_SECRET_KEY_PREVIOUS_EXPIRES_AT` environment variables support a rolling-key rotation window of up to seven days. During rotation, tokens signed with the previous key remain valid only until the deadline. Both settings are validated at startup: the previous key must differ from the current key, be at least 32 characters, and have a deadline no more than seven days in the future.

### Login Rate Limiting

Login attempts are tracked per username (case-insensitive) in PostgreSQL, shared across all API workers. Five failed attempts within any 15-minute window lock out further attempts with a `429 Too Many Requests` response and a `Retry-After` header. The check runs before bcrypt comparison to prevent cost-amplification denial-of-service.

---

## Authorization

Three roles are supported: `parent`, `tutor`, and `admin`. Role enforcement is applied server-side via FastAPI dependency injection (`require_role()`). Role is embedded in the JWT and cannot be elevated through any user-facing endpoint.

Match lifecycle transitions are enforced by a server-side state machine; clients cannot skip or reverse states. Tutor capacity limits are checked before a match invitation is accepted.

---

## Middleware Stack

The following middleware layers are applied in order (outermost first):

| Layer | Purpose |
|---|---|
| CORS | Explicit origin allow-list; wildcards disallowed when `credentials=true` |
| RequestID | Injects `X-Request-ID` (UUID) for log correlation |
| BodySizeLimit | Rejects payloads exceeding `MAX_REQUEST_BODY_BYTES` (default 50 MB) |
| SecurityHeaders | Sets `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Cache-Control: no-store`, and a restrictive Content-Security-Policy |
| AccessLog | Structured JSON logging with client IP, method, path, status, and duration |
| UserConcurrencyQuota | Per-authenticated-user DB connection cap (default 5, `DB_PER_USER_QUOTA`); returns `429` with `Retry-After: 1` when exceeded |
| RateLimitMiddleware | Per-path limits (login: 10/60 s, register: 5/60 s, refresh: 20/60 s, admin reset: 5/3600 s, subjects: 30/60 s, default: 60/60 s); fail-closed on critical paths |

Nginx applies an additional edge limit of 20 r/s with a burst of 40 before requests reach FastAPI.

---

## Input Validation and Output Sanitization

All API inputs are validated by Pydantic v2. Passwords must be at least 10 characters and include both letters and digits. Usernames are validated against a regex pattern.

Fields named `password`, `token`, or `secret` are scrubbed from validation error responses and structured logs before emission. Nested Pydantic `ValidationError` objects have their `input` and `ctx` keys stripped and their `msg` fields sanitized, preventing credential leakage through `422` responses.

Unhandled exceptions return a generic `500` response body; the exception class is collapsed to `"InternalError"` in logs. Stack traces are never exposed to clients. The `X-Request-ID` header is present on `500` responses to allow log correlation without exposing internal detail.

---

## Cryptography

| Concern | Mechanism |
|---|---|
| Password storage | bcrypt via `bcrypt==4.2.1`; cost factor tuned for the deployment environment |
| Token signing | HS256 (PyJWT 2.9.0); `alg=none` blocked |
| Transport | TLS required; `COOKIE_SECURE=true` enforced when `DEBUG=false` |
| Secrets at rest | Injected via Docker secrets (files), never via environment variables |

The application does not implement TLS termination itself. A reverse proxy (e.g., Nginx with a valid certificate, Caddy, or a cloud load balancer) must terminate TLS in front of the web container.

---

## Container and Deployment Hardening

All containers run with:
- `security_opt: no-new-privileges:true`
- `cap_drop: ALL`
- Non-root users (API: UID 1000, Nginx: UID 101, PostgreSQL: UID 70)
- Base images pinned by SHA-256 digest

Resource limits are applied per service (API/DB: 512 MB RAM, 1.0 CPU; Worker: 256 MB RAM, 0.5 CPU). The database port is not bound to the host in production. API and web containers are assigned fixed IPs on a custom bridge network for reliable `X-Forwarded-For` validation.

---

## Secrets Management

The following values must be supplied via Docker secrets, not environment variables:

| Secret file | Content |
|---|---|
| `secrets/db_password.txt` | PostgreSQL password |
| `secrets/jwt_secret_key.txt` | JWT signing key (≥ 32 characters) |
| `secrets/admin_password.txt` | Bootstrap admin password (≥ 16 characters, all four character classes) |
| `secrets/jwt_secret_key_previous.txt` | Previous JWT key during rotation (optional) |

The application startup routine rejects placeholder values (`change-me`, `change-me-in-production`) for all critical secrets. The admin username must not be the literal string `admin`.

The `secrets/` directory and all `.env` files are excluded from version control via `.gitignore`. Pre-commit hooks (`gitleaks v8.18.4`, `detect-private-key`) are configured to catch secret-shaped patterns before a commit is recorded.

---

## Logging and Audit Trail

All API requests produce a structured JSON log entry containing the request ID, HTTP method, path, status code, duration in milliseconds, client IP, and user agent. Sensitive fields are scrubbed before the log entry is written.

Privileged actions (user role changes, password resets, admin-initiated operations) are recorded in the `audit_log` table with actor identity, action type, resource ID, and timestamp. Actor foreign keys are set to `NULL` rather than deleted when a user account is removed, preserving the audit record.

---

## Known Limitations

The following items represent acknowledged gaps relative to a fully hardened production system. They are documented here rather than treated as undisclosed risks.

**Architectural constraints (course requirements):**
- The project was specified with a Microsoft Access front end for the database tier. The current codebase targets PostgreSQL, but some design decisions reflect that origin.
- No WebSocket support; real-time messaging uses polling.
- No CI/CD pipeline; testing is manual.
- No TypeScript; the frontend is plain JavaScript (Vue 3).

**Deployment prerequisites not handled by this repository:**
- TLS termination must be provided externally.
- `DEBUG=false` and `COOKIE_SECURE=true` must be set before any public exposure.
- `ENABLE_DOCS` must remain `false` (the default) in production; the startup validator hard-fails if `ENABLE_DOCS=true` and `DEBUG=false` are set simultaneously.
- CORS origins must be set to an explicit allow-list, not a wildcard.

**Not yet implemented:**
- PKCE or OAuth 2.0 for third-party login.
- Asymmetric JWT signing (RS256/ES256) for multi-service deployments.
- Automated vulnerability scanning in CI.
- Password history enforcement (prevents reuse of the last N passwords).
- Multi-factor authentication.

These are not design oversights; they are deferred work that falls outside the scope of the course deliverable.

---

## Required Environment Configuration for Production

The startup validator enforces the following before the API serves any requests:

| Check | Requirement |
|---|---|
| `JWT_SECRET_KEY` | ≥ 32 characters; no placeholder values |
| `COOKIE_SECURE` | Must be `true` when `DEBUG=false` |
| `ENABLE_DOCS` | Must not be `true` when `DEBUG=false`; rejected by startup validator |
| `ADMIN_PASSWORD` | ≥ 16 characters; must include lowercase, uppercase, digit, and symbol |
| `ADMIN_USERNAME` | Must not be `admin` or a placeholder |
| `JWT_SECRET_KEY_PREVIOUS` | If set: ≥ 32 characters, differs from current key, expiry within 7 days |
| `CORS_ORIGINS` | No wildcards when credentials are enabled |

The API will refuse to start if any of these checks fail.

---

## Token Rotation Procedure

1. Generate a new secret key (≥ 32 random characters).
2. Move the current key to `secrets/jwt_secret_key_previous.txt`.
3. Write the new key to `secrets/jwt_secret_key.txt`.
4. Set `JWT_SECRET_KEY_PREVIOUS_EXPIRES_AT` to a timestamp at most seven days in the future.
5. Restart the API and worker containers.
6. After the deadline passes, remove the previous key file and unset the expiry variable, then restart again.

All active sessions will remain valid through the rotation window and will be re-signed with the new key on their next refresh.

---

*This document reflects the state of the codebase as of the project's final submission. It will be updated if significant changes are made post-submission.*
