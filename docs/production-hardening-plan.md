# TMRP Production Hardening Plan

> **Date:** 2026-04-06  
> **Scope:** Harden the existing TMRP codebase for production-grade deployment  
> **Constraint:** MS Access as database is a project requirement (SQL course); this plan works within that boundary  
> **Principle:** Separation of concerns — each change is isolated, testable, and introduces minimal coupling

---

## Table of Contents

1. [Priority Matrix](#1-priority-matrix)
2. [Phase 1 — Security Hardening](#2-phase-1--security-hardening)
3. [Phase 2 — Observability & Diagnostics](#3-phase-2--observability--diagnostics)
4. [Phase 3 — Reliability & Resilience](#4-phase-3--reliability--resilience)
5. [Phase 4 — API Defensive Layer](#5-phase-4--api-defensive-layer)
6. [Phase 5 — Frontend Hardening](#6-phase-5--frontend-hardening)
7. [Phase 6 — Deployment & Operations](#7-phase-6--deployment--operations)
8. [Residual Technical Debt](#8-residual-technical-debt)
9. [Implementation Sequence](#9-implementation-sequence)

---

## 1. Priority Matrix

| ID | Item | Severity | Effort | Phase |
|----|------|----------|--------|-------|
| S1 | CORS over-permissive (`*` methods/headers) | Critical | Low | 1 |
| S2 | Global exception handlers (500, 422) | Critical | Low | 1 |
| S3 | Security response headers (HSTS, CSP, X-Frame) | High | Low | 1 |
| S4 | Password strength validation | High | Low | 1 |
| S5 | Login rate limiting | High | Medium | 1 |
| S6 | JWT `iat`/`jti` claims + refresh token | Medium | Medium | 1 |
| O1 | Request ID middleware | Critical | Low | 2 |
| O2 | Request/response logging middleware | Critical | Medium | 2 |
| O3 | Structured JSON logging | High | Medium | 2 |
| O4 | Health check endpoint | Medium | Low | 2 |
| R1 | Database connection validation & timeout | High | Low | 3 |
| R2 | Transaction management abstraction | High | Medium | 3 |
| R3 | Graceful shutdown (lifespan cleanup) | Medium | Low | 3 |
| R4 | Huey task error handling & retry | Medium | Medium | 3 |
| A1 | Global rate limiter middleware | High | Medium | 4 |
| A2 | Input size limits & request timeout | Medium | Low | 4 |
| A3 | API versioning header | Low | Low | 4 |
| F1 | Global Vue error handler + boundary | High | Low | 5 |
| F2 | Axios retry with exponential backoff | High | Low | 5 |
| F3 | Session validation on app mount | High | Low | 5 |
| F4 | `.env.production` + build config | Medium | Low | 5 |
| D1 | Dockerfile + docker-compose | Medium | Medium | 6 |
| D2 | Environment validation on startup | Medium | Low | 6 |
| D3 | Secrets management guidance | Low | Low | 6 |

---

## 2. Phase 1 — Security Hardening

### S1: Restrict CORS Configuration

**File:** `tutor-platform-api/app/main.py` (lines 65-72)

**Current state:** `allow_methods=["*"]` and `allow_headers=["*"]` — accepts any HTTP method and header from allowed origins.

**Change:**

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)
```

**Rationale:** Explicit allowlists prevent browsers from sending unexpected methods (TRACE, CONNECT) or headers that the API never inspects.

---

### S2: Global Exception Handlers

**File:** `tutor-platform-api/app/exceptions.py`

Add handlers for unhandled exceptions and Pydantic validation errors so the API never leaks stack traces.

```python
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning("Validation error on %s %s: %s", request.method, request.url.path, exc.errors())
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "data": None,
            "message": "輸入資料格式錯誤",
            "errors": exc.errors(),
        },
    )

async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "data": None, "message": exc.detail or "HTTP 錯誤"},
    )

async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"success": False, "data": None, "message": "伺服器內部錯誤"},
    )
```

Register in `main.py`:

```python
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)
```

**Separation of concerns:** Exception handlers remain in `exceptions.py`; `main.py` only wires them.

---

### S3: Security Response Headers

**New file:** `tutor-platform-api/app/middleware/security_headers.py`

```python
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        return response
```

Register in `main.py` before CORS middleware.

---

### S4: Password Strength Validation

**File:** `tutor-platform-api/app/models/auth_model.py`

Add a Pydantic field validator to `RegisterRequest`:

```python
from pydantic import field_validator
import re

class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str
    display_name: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("密碼長度至少 8 個字元")
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("密碼須同時包含英文字母與數字")
        return v
```

**Scope:** Validation lives in the model layer — routers are untouched.

---

### S5: Login Rate Limiting

**New file:** `tutor-platform-api/app/middleware/rate_limit.py`

Use an in-memory sliding window (no external dependency). Scoped to auth endpoints only.

```python
import time
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class LoginRateLimitMiddleware(BaseHTTPMiddleware):
    """Rate-limit login attempts by client IP. 10 attempts per 60 seconds."""

    def __init__(self, app, max_attempts: int = 10, window_seconds: int = 60):
        super().__init__(app)
        self.max_attempts = max_attempts
        self.window = window_seconds
        self.attempts: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request, call_next):
        if request.url.path == "/api/auth/login" and request.method == "POST":
            ip = request.client.host
            now = time.time()
            # Prune expired entries
            self.attempts[ip] = [t for t in self.attempts[ip] if now - t < self.window]
            if len(self.attempts[ip]) >= self.max_attempts:
                return JSONResponse(
                    status_code=429,
                    content={"success": False, "data": None, "message": "登入嘗試過於頻繁，請稍後再試"},
                )
            self.attempts[ip].append(now)
        return await call_next(request)
```

**Trade-off:** In-memory state resets on restart and does not share across workers. Acceptable for single-process uvicorn deployment (which is the TMRP case). For multi-worker, replace with Redis-backed limiter.

---

### S6: JWT Hardening — `iat`, `jti`, Refresh Token

**File:** `tutor-platform-api/app/utils/security.py`

Add `iat` (issued-at) and `jti` (unique token ID) claims:

```python
import uuid

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.jwt_expire_minutes))
    to_encode.update({
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),
    })
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
```

**Refresh token flow** (new endpoint `POST /api/auth/refresh`):

1. On login, return both `access_token` (short-lived, 15 min) and `refresh_token` (long-lived, 7 days).
2. `refresh_token` is a separate JWT with type claim `"type": "refresh"`.
3. Client stores refresh token in memory (not localStorage) and uses it to obtain new access tokens.
4. `decode_access_token` rejects tokens with `"type": "refresh"`.

**New file:** `tutor-platform-api/app/routers/auth.py` — add `/refresh` endpoint.

**Frontend change:** Axios interceptor catches 401, calls `/refresh`, replays original request.

---

## 3. Phase 2 — Observability & Diagnostics

### O1: Request ID Middleware

**New file:** `tutor-platform-api/app/middleware/request_id.py`

```python
import uuid
from starlette.middleware.base import BaseHTTPMiddleware

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
```

Every log entry within a request can reference `request.state.request_id` for correlation. This middleware is stateless and has no dependency on other components.

---

### O2: Request/Response Logging Middleware

**New file:** `tutor-platform-api/app/middleware/access_log.py`

```python
import time
from starlette.middleware.base import BaseHTTPMiddleware

class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "request",
            extra={
                "request_id": getattr(request.state, "request_id", "-"),
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 1),
                "client_ip": request.client.host,
                "user_agent": request.headers.get("user-agent", "-"),
            },
        )
        return response
```

**Depends on:** O1 (request ID). Must be registered after `RequestIDMiddleware` in the middleware stack.

---

### O3: Structured JSON Logging

**File:** `tutor-platform-api/app/utils/logger.py`

Replace the plaintext formatter with a JSON formatter for machine-parseable logs. Keep the console handler human-readable for development.

```python
import json
import logging

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        # Merge extra fields from AccessLogMiddleware
        for key in ("method", "path", "status", "duration_ms", "client_ip"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)
        return json.dumps(log_entry, ensure_ascii=False)
```

**Apply to file handler only.** Console handler keeps the existing human-readable format. Controlled by `LOG_FORMAT` env var (`json` or `text`).

---

### O4: Health Check Endpoint

**File:** `tutor-platform-api/app/routers/health.py` (new)

```python
from fastapi import APIRouter, Depends
from app.database import get_db

router = APIRouter(tags=["health"])

@router.get("/health")
def health_check(conn=Depends(get_db)):
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM Users")
        cursor.fetchone()
        return {"status": "healthy", "database": "connected"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "database": "disconnected"})
```

**Purpose:** Load balancers, container orchestrators, and monitoring tools poll this endpoint. Returns 200 or 503.

---

## 4. Phase 3 — Reliability & Resilience

### R1: Database Connection Validation & Timeout

**File:** `tutor-platform-api/app/database.py`

Add connection timeout and pre-use validation:

```python
def get_connection(retries=3, delay=0.5):
    conn_str = (
        f"DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};"
        f"DBQ={settings.access_db_path};"
        f"TIMEOUT=5;"          # <-- connection timeout
    )
    # ... existing retry logic ...
    conn.timeout = 10          # <-- query timeout (seconds)
    return conn

def get_db():
    conn = get_connection()
    try:
        # Validate connection is alive
        conn.cursor().execute("SELECT 1")
        yield conn
    except Exception:
        conn.close()
        raise
    finally:
        conn.close()
```

**Scope:** Only `database.py` changes. All downstream code is unaffected.

---

### R2: Transaction Management Abstraction

**New file:** `tutor-platform-api/app/database_tx.py`

Provide a context manager that repositories can use for multi-statement transactions:

```python
from contextlib import contextmanager

@contextmanager
def transaction(conn):
    """
    Usage:
        with transaction(conn):
            repo.create(...)
            repo.update(...)
    Auto-commits on success, rolls back on exception.
    """
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = True
```

**Current state:** Every `BaseRepository.execute()` calls `conn.commit()` immediately. For single-statement operations this is fine. The transaction wrapper is opt-in for routers that need atomicity across multiple operations (e.g., match creation + capacity check).

**Migration:** No existing code breaks. Routers that need atomicity adopt `with transaction(conn):` explicitly.

---

### R3: Graceful Shutdown

**File:** `tutor-platform-api/app/main.py` (lifespan)

```python
@asynccontextmanager
async def lifespan(application: FastAPI):
    # Startup
    logger.info("API starting")
    ensure_admin_user_safe()
    yield
    # Shutdown
    logger.info("API shutting down — flushing logs")
    logging.shutdown()
```

Minimal change. If Huey is run in-process in the future, its consumer should also be stopped here.

---

### R4: Huey Task Error Handling & Retry

**File:** `tutor-platform-api/app/tasks/*.py`

Wrap each task with retry and error reporting:

```python
@huey.task(retries=3, retry_delay=10)
def import_csv_task(table_name: str, csv_content: str):
    conn = get_connection()
    try:
        # ... existing logic ...
    except Exception as e:
        logger.exception("Task import_csv_task failed for table=%s", table_name)
        raise  # Huey retries on exception
    finally:
        conn.close()
```

- Add `retries=3, retry_delay=10` to `@huey.task()` decorator.
- Ensure `finally: conn.close()` exists on every task (already present in most).
- Log failures with full stack trace.

---

## 5. Phase 4 — API Defensive Layer

### A1: Global Rate Limiter

**New file:** `tutor-platform-api/app/middleware/rate_limit.py`

Extend the login rate limiter (S5) into a general-purpose middleware with configurable per-path limits:

```python
RATE_LIMITS = {
    "/api/auth/login": (10, 60),     # 10 req / 60s
    "/api/auth/register": (5, 60),   # 5 req / 60s
    "default": (60, 60),             # 60 req / 60s for all other endpoints
}
```

**Separation:** Rate limit config is declarative. The middleware reads it; routes are unaware.

---

### A2: Request Body Size Limit & Timeout

**File:** `tutor-platform-api/app/main.py`

Uvicorn already has a default `--limit-max-request-size` (16 KB for headers). For body size:

```python
from starlette.middleware.trustedhost import TrustedHostMiddleware

# In main.py — limit request body to 10 MB
app.add_middleware(
    # Uvicorn flag: --limit-concurrency 100
)
```

Alternatively, set in the uvicorn startup command:

```bash
uvicorn app.main:app --limit-max-request-size 10485760 --timeout-keep-alive 30
```

For per-route limits (e.g., CSV upload), use FastAPI's `UploadFile` with `max_size` validation in the router.

---

### A3: API Version Header

Lightweight — no URL prefixing, just a response header for client awareness:

```python
# In SecurityHeadersMiddleware
response.headers["X-API-Version"] = "0.1.0"
```

---

## 6. Phase 5 — Frontend Hardening

### F1: Global Vue Error Handler

**File:** `tutor-platform-web/src/main.js`

```javascript
const app = createApp(App)
app.use(createPinia())
app.use(router)

// Global error handler — catches unhandled errors in components
app.config.errorHandler = (err, instance, info) => {
  console.error('[Vue Error]', err, info)
  const toast = useToastStore()
  toast.error('發生未預期的錯誤')
}

// Catch unhandled promise rejections
window.addEventListener('unhandledrejection', (event) => {
  console.error('[Unhandled Rejection]', event.reason)
})

app.mount('#app')
```

---

### F2: Axios Retry with Exponential Backoff

**File:** `tutor-platform-web/src/api/index.js`

Add retry logic for transient network errors (no new dependency):

```javascript
async function retryRequest(axiosInstance, config, retries = 2) {
  for (let i = 0; i <= retries; i++) {
    try {
      return await axiosInstance.request(config)
    } catch (err) {
      const isRetryable =
        !err.response || err.response.status >= 500 || err.code === 'ECONNABORTED'
      if (i === retries || !isRetryable) throw err
      await new Promise((r) => setTimeout(r, 1000 * 2 ** i))
    }
  }
}
```

Integrate into the response error interceptor for 5xx and network errors only. Never retry 4xx (client errors).

---

### F3: Session Validation on App Mount

**File:** `tutor-platform-web/src/App.vue`

```javascript
import { onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'

onMounted(async () => {
  const auth = useAuthStore()
  if (auth.token) {
    try {
      const user = await authApi.getMe()
      auth.setAuth(auth.token, user)
    } catch {
      auth.logout()
    }
  }
})
```

**Purpose:** On every page load/refresh, validate that the stored token is still valid. If the backend rejects it, clear local state and redirect to login.

---

### F4: Environment & Build Configuration

**New file:** `tutor-platform-web/.env.production`

```env
VITE_API_BASE_URL=/api
```

**New file:** `tutor-platform-web/.env.example`

```env
VITE_API_BASE_URL=http://localhost:8000
```

**File:** `tutor-platform-web/vite.config.js` — add build optimizations:

```javascript
export default defineConfig({
  // ... existing config ...
  build: {
    sourcemap: false,     // No source maps in production
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['vue', 'vue-router', 'pinia', 'axios'],
          charts: ['chart.js', 'vue-chartjs'],
        },
      },
    },
  },
})
```

---

## 7. Phase 6 — Deployment & Operations

### D1: Dockerfile & docker-compose (Optional)

Provide containerized deployment for consistent environments. Two services: `api` and `worker`.

```yaml
# docker-compose.yml
services:
  api:
    build: ./tutor-platform-api
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    env_file: ./tutor-platform-api/.env

  worker:
    build: ./tutor-platform-api
    command: huey_consumer app.worker.huey
    volumes:
      - ./data:/app/data
    env_file: ./tutor-platform-api/.env

  web:
    build: ./tutor-platform-web
    ports:
      - "80:80"
    depends_on:
      - api
```

**Note:** MS Access requires Windows containers or Wine in Linux. For this project, a Windows-native deployment (PM2, NSSM, or Task Scheduler) is more practical.

### D2: Environment Validation on Startup

**File:** `tutor-platform-api/app/config.py`

```python
class Settings(BaseSettings):
    # ... existing fields ...

    @model_validator(mode="after")
    def validate_security_defaults(self):
        if self.jwt_secret_key == "change-me-in-production":
            raise ValueError("JWT_SECRET_KEY must be changed from default before deployment")
        if self.admin_password == "admin123":
            import warnings
            warnings.warn("ADMIN_PASSWORD is using default value", stacklevel=2)
        return self
```

**Current state:** `main.py` logs warnings but continues. This validator makes the insecure JWT secret a hard failure.

### D3: Secrets Management Guidance

Document in project README:

- Generate JWT secret: `python -c "import secrets; print(secrets.token_hex(32))"`
- Never commit `.env` to git (already in `.gitignore`)
- For team deployments: use Windows Credential Manager or environment-specific `.env` files

---

## 8. Residual Technical Debt

Items deliberately deferred as out of scope for this hardening plan:

| Item | Reason for Deferral |
|------|---------------------|
| **MS Access → PostgreSQL migration** | Course requirement mandates Access; migration is a separate initiative |
| **TypeScript migration (frontend)** | High effort, orthogonal to security/reliability; plan separately |
| **Full test suite** | Separate testing plan recommended; not a hardening concern |
| **CI/CD pipeline** | Depends on team's hosting decision; document after Phase 6 |
| **WebSocket for real-time messaging** | Feature addition, not hardening |
| **JWT in httpOnly cookie** | Requires backend cookie handling + CSRF token; deferred due to complexity vs. risk for a demo app with no public exposure |
| **Connection pooling** | MS Access ODBC does not support pooling natively; pyodbc connections are lightweight enough for expected load |
| **Log aggregation (ELK/Datadog)** | Overkill for single-server deployment; structured JSON logs (O3) enable future integration |
| **Pagination optimization** | `fetch_paginated` loads all rows then slices; acceptable for Access DB row counts (<10K) |

---

## 9. Implementation Sequence

```
Week 1 ─── Phase 1: Security Hardening
  │  S1  Restrict CORS                          (30 min)
  │  S2  Global exception handlers               (1 hr)
  │  S3  Security response headers middleware     (30 min)
  │  S4  Password strength validator              (30 min)
  │  S5  Login rate limiter middleware             (1 hr)
  │  S6  JWT iat/jti + refresh token              (2 hr)
  │
Week 1 ─── Phase 2: Observability
  │  O1  Request ID middleware                    (30 min)
  │  O2  Access log middleware                    (1 hr)
  │  O3  JSON log formatter                       (1 hr)
  │  O4  Health check endpoint                    (30 min)
  │
Week 2 ─── Phase 3: Reliability
  │  R1  Connection validation & timeout          (30 min)
  │  R2  Transaction context manager              (1 hr)
  │  R3  Graceful shutdown                        (15 min)
  │  R4  Huey task retry + error logging          (1 hr)
  │
Week 2 ─── Phase 4: API Defensive Layer
  │  A1  Global rate limiter                      (1 hr)
  │  A2  Request body size + timeout config       (30 min)
  │  A3  API version header                       (15 min)
  │
Week 2 ─── Phase 5: Frontend Hardening
  │  F1  Vue global error handler                 (30 min)
  │  F2  Axios retry logic                        (1 hr)
  │  F3  Session validation on mount              (30 min)
  │  F4  .env.production + build config           (30 min)
  │
Week 3 ─── Phase 6: Deployment
     D1  Dockerfiles (optional)                   (2 hr)
     D2  Startup env validation                   (30 min)
     D3  Secrets management docs                  (30 min)
```

**Total estimated effort:** ~18 hours across 2-3 weeks

---

## Middleware Registration Order

The final middleware stack in `main.py` should be registered in this order (Starlette processes them bottom-to-top, so the first registered is the outermost):

```python
# 1. Request ID (outermost — assigns ID before anything else)
app.add_middleware(RequestIDMiddleware)

# 2. Security headers
app.add_middleware(SecurityHeadersMiddleware)

# 3. Access logging (needs request ID from step 1)
app.add_middleware(AccessLogMiddleware)

# 4. Rate limiting
app.add_middleware(LoginRateLimitMiddleware)

# 5. CORS (innermost of custom middleware — must be close to routes)
app.add_middleware(CORSMiddleware, ...)
```

---

## New File Structure

```
tutor-platform-api/
├── app/
│   ├── middleware/           ← NEW directory
│   │   ├── __init__.py
│   │   ├── request_id.py    ← O1
│   │   ├── access_log.py    ← O2
│   │   ├── rate_limit.py    ← S5 + A1
│   │   └── security_headers.py  ← S3
│   ├── routers/
│   │   └── health.py        ← O4 (new)
│   ├── database_tx.py       ← R2 (new)
│   └── ... (existing files modified in-place)
```

Frontend changes are in-place edits only — no new files except `.env.production` and `.env.example`.
