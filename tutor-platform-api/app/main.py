import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.shared.infrastructure.config import settings
from app.shared.domain.exceptions import DomainException
from app.middleware.access_log import AccessLogMiddleware
from app.middleware.body_size_limit import BodySizeLimitMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.user_quota import UserConcurrencyQuotaMiddleware

# Routers from each bounded context
from app.shared.api.health_router import router as health_router
from app.identity.api.router import router as auth_router
from app.catalog.api.tutor_router import router as tutor_router
from app.catalog.api.student_router import router as student_router
from app.catalog.api.subject_router import router as subject_router
from app.matching.api.router import router as match_router
from app.teaching.api.session_router import router as session_router
from app.teaching.api.exam_router import router as exam_router
from app.review.api.router import router as review_router
from app.messaging.api.router import router as message_router
from app.analytics.api.router import router as stats_router
from app.admin.api.router import router as admin_router

from app.shared.infrastructure.logger import setup_logger

logger = setup_logger()


# ─── Exception Handlers ───

async def domain_exception_handler(request, exc: DomainException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "data": None, "message": exc.message},
    )


# HIGH-2 / HIGH-4: fields whose raw value must never reach logs or the 422
# response body. Some Pydantic validators (e.g. regex, string-length) embed
# the offending value inside `msg`, so dropping `input`/`ctx` alone is not
# enough — we also scrub `msg` to a generic string whenever the failing
# field name matches this list.
_SENSITIVE_FIELD_NAMES: frozenset[str] = frozenset({
    "password", "old_password", "new_password", "admin_password",
    "token", "access_token", "refresh_token", "reset_token",
    "jwt", "secret", "secret_key", "api_key", "authorization",
})


def _is_sensitive_loc(loc) -> bool:
    for part in loc:
        if isinstance(part, str) and part.lower() in _SENSITIVE_FIELD_NAMES:
            return True
    return False


def _safe_msg(e: dict) -> str:
    """Return `msg` with the raw input scrubbed out for sensitive fields.

    For non-sensitive fields Pydantic's message is preserved so operators
    keep a useful triage signal. For sensitive fields we return a generic
    replacement — a password that fails `min_length` otherwise leaks its
    length via "String should have at least N characters", and regex
    failures can echo fragments of the value itself.
    """
    loc = e.get("loc") or ()
    if _is_sensitive_loc(loc):
        return "value failed validation"
    return e.get("msg", "")


def _redact_validation_errors(errors):
    # HIGH-2: Pydantic error dicts embed the raw `input` under any failed field.
    # Logging them verbatim persists plaintext passwords and refresh tokens
    # (OWASP ASVS V7.1.1). Drop `input`/`ctx` entirely and scrub `msg` for
    # sensitive fields — the triage signal we actually need is just
    # {loc, type, msg} with value fragments stripped.
    redacted = []
    for e in errors:
        loc = e.get("loc") or ()
        redacted.append({
            "loc": [str(p) for p in loc],
            "type": e.get("type", ""),
            "msg": _safe_msg(e),
        })
    return redacted


async def validation_exception_handler(request, exc: RequestValidationError):
    logger.warning(
        "Validation error on %s %s: %s",
        request.method, request.url.path, _redact_validation_errors(exc.errors()),
    )
    sanitized = [
        {
            "field": str(e["loc"][-1]) if e.get("loc") else "",
            "message": _safe_msg(e),
        }
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "data": None,
            "message": "輸入資料格式錯誤",
            "errors": sanitized,
        },
    )


async def http_exception_handler(request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "data": None, "message": exc.detail or "HTTP 錯誤"},
    )


_LEAKY_EXCEPTION_TYPES: frozenset[str] = frozenset({
    # Exception classes whose name alone reveals the backing technology
    # (DB driver, ORM, ...). Collapse to a generic label in structured logs
    # so log sinks shipped to 3rd parties (Sentry, ELK) don't double as a
    # stack fingerprint. The full traceback still goes to server-local logs
    # via logger.exception — operators retain root-cause detail.
    "UndefinedTable", "UndefinedColumn", "IntegrityError", "DataError",
    "OperationalError", "ProgrammingError", "InterfaceError",
    "InternalError", "NotSupportedError", "DatabaseError",
    "DuplicateTable", "ForeignKeyViolation", "UniqueViolation",
})


async def unhandled_exception_handler(request, exc: Exception):
    # Surface the request_id injected by RequestIDMiddleware so user-reported
    # errors can be cross-referenced against the structured logs.
    request_id = getattr(request.state, "request_id", None)
    exc_type = type(exc).__name__
    logged_type = "InternalError" if exc_type in _LEAKY_EXCEPTION_TYPES else exc_type
    # Don't interpolate str(exc) into the message — exception messages from
    # libraries (especially DB drivers) frequently carry query fragments,
    # constraint names and server paths that become searchable in log
    # aggregators. The traceback attached by logger.exception stays on
    # the server-local handler for operator debugging.
    logger.exception(
        "Unhandled exception on %s %s [request_id=%s] type=%s",
        request.method, request.url.path, request_id, logged_type,
    )
    body = {"success": False, "data": None, "message": "伺服器內部錯誤"}
    # SEC-L04: expose request_id only in the header — keeps it available for
    # support correlation without surfacing it in the JSON body where it
    # could aid request-fingerprinting attacks.
    headers = {"X-Request-ID": request_id} if request_id else None
    return JSONResponse(status_code=500, content=body, headers=headers)


# Bug #17: container startup ordering — must not pass the healthcheck
# before the DB schema is initialized, or docker-compose's service_healthy
# condition will let dependent services (web) connect too early. Since
# init_pool + create_schema both run synchronously before the yield below,
# FastAPI does not start serving requests until this coroutine yields;
# the only requirement is that docker healthcheck's start_period is greater
# than initialization time. docker-compose.yml sets start_period=30s, which
# covers the first cold start.
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API server starting")
    # Access tokens are not revoked on logout; only refresh-token JTIs are
    # blacklisted. Building an access-token blacklist is explicitly rejected
    # here — it would require a DB hit on every authenticated request, which
    # erases the main reason for choosing short-lived JWTs. Instead, we lean
    # entirely on the short TTL as the bound on a hijacked token's window.
    # The default in config.py is 5 minutes; the 10-minute cap below is the
    # absolute upper bound we are willing to accept as defence in depth.
    # `raise` (not `assert`) so `python -O` cannot strip the check.
    if settings.jwt_expire_minutes > 10:
        raise RuntimeError(
            f"JWT_EXPIRE_MINUTES must be <= 10 (got {settings.jwt_expire_minutes}) "
            "because access tokens are not revoked on logout."
        )
    from app.shared.infrastructure.database import init_pool, close_pool, get_connection, release_connection

    init_pool()
    logger.info("PostgreSQL connection pool initialized")

    try:
        from app.init_db import create_schema, seed_subjects, ensure_admin_user, verify_bootstrap

        conn = get_connection()
        try:
            create_schema(conn)
            seed_subjects(conn)
            ensure_admin_user(conn, settings)
            verify_bootstrap(conn, settings)
        finally:
            release_connection(conn)
        logger.info("Database initialization and admin-user check complete")
    except Exception as e:
        # Crash on init failure rather than serve requests in a half-initialized state.
        logger.exception("Database initialization failed; refusing to start: %s", e)
        raise
    # SEC-L03: periodic cleanup so rate-limit records don't accumulate
    # during zero-traffic windows (the middleware-driven cleanup only fires
    # on incoming requests).
    from app.middleware.rate_limit import run_periodic_cleanup
    cleanup_task = asyncio.create_task(run_periodic_cleanup())

    yield
    # Shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    close_pool()
    logger.info("API server shutting down — flushing logs")
    logging.shutdown()


tags_metadata = [
    {"name": "auth", "description": "使用者認證：註冊、登入、取得個人資訊"},
    {"name": "tutors", "description": "家教管理：搜尋、個人檔案、科目、時段、隱私設定"},
    {"name": "students", "description": "子女管理：新增、編輯、列出子女資料"},
    {"name": "subjects", "description": "科目列表：查詢系統可用科目（不需登入）"},
    {"name": "matches", "description": "配對管理：邀請、狀態轉換（含完整狀態機）、詳情查詢"},
    {"name": "sessions", "description": "上課日誌：新增、修改、查看修改紀錄"},
    {"name": "exams", "description": "考試紀錄：新增、修改、查詢學生考試成績"},
    {"name": "reviews", "description": "三向評價：家長→老師、老師→家長、老師→學生，含 7 天鎖定機制"},
    {"name": "messages", "description": "即時通訊：建立對話、傳送與接收訊息"},
    {"name": "stats", "description": "統計分析：家教收入、家長支出、學生成績趨勢"},
    {"name": "admin", "description": "系統管理：使用者管理、資料匯入匯出、假資料生成、系統狀態"},
    {"name": "health", "description": "健康檢查：API 與資料庫連線狀態"},
]

if settings.debug:
    # DEBUG=true exposes /docs, /redoc and /openapi.json — these publish the
    # full route inventory and schemas and MUST NOT be enabled in production.
    # Log loudly at startup so a misconfigured deploy is obvious in the logs
    # rather than silently shipping an introspectable attack surface.
    logger.warning(
        "DEBUG=true: /docs, /redoc, /openapi.json are PUBLIC. "
        "Never enable this in production — the full route and schema "
        "inventory is exposed to anonymous callers."
    )

app = FastAPI(
    title="家教媒合與評價平台 API",
    description="TMRP — Tutor Matching and Rating Platform\n\n"
    "提供家長搜尋家教、配對媒合、上課管理、三向評價等完整功能的 RESTful API。",
    version="0.2.0",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
    # Disable interactive docs in production unless DEBUG=true is set explicitly.
    # Avoids exposing the full route inventory to anonymous scanners.
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
)

# ─── Middleware (Starlette: last registered = outermost; requests flow outer-in) ───
# 7. Rate limiting (closest to the route -> registered first -> innermost)
app.add_middleware(RateLimitMiddleware)
# 6. Per-user concurrency quota (I-07). Registered after RateLimitMiddleware
#    so in the request path it runs just outside the per-path bucket: any
#    unauthenticated flood still hits RateLimitMiddleware, and any single
#    authenticated caller is additionally bounded so they cannot monopolise
#    DB pool slots across paths.
app.add_middleware(UserConcurrencyQuotaMiddleware)
# 5. Access logging (needs request_id, so it lives inside RequestID)
app.add_middleware(AccessLogMiddleware)
# 4. Security headers
app.add_middleware(SecurityHeadersMiddleware)
# 3. Body-size limit — rejects oversized payloads before the handler reads them;
#    lives inside RequestID so the rejection log line carries the request_id.
app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes)
# 2. Request ID
app.add_middleware(RequestIDMiddleware)
# 1. CORS (outermost — registered last -> runs first, so all responses carry CORS headers)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    # SEC-C02 / M-01: auth migrated to HttpOnly cookies. allow_credentials
    # must be True so the browser sends cookies on cross-origin requests.
    # CSRF is mitigated by SameSite=Lax on all auth cookies.
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    # HIGH-3: X-Requested-With is attached by the SPA on all mutating
    # requests to force a CORS preflight — cross-origin CSRF attempts from
    # non-whitelisted origins cannot pass the preflight. Must be listed here
    # so legitimate browser preflights succeed.
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)

# ─── Centralised exception handlers ───
app.add_exception_handler(DomainException, domain_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# ─── Mount routers ───
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(tutor_router)
app.include_router(student_router)
app.include_router(subject_router)
app.include_router(match_router)
app.include_router(session_router)
app.include_router(exam_router)
app.include_router(review_router)
app.include_router(message_router)
app.include_router(stats_router)
app.include_router(admin_router)


@app.get("/")
async def root():
    return {"message": "家教媒合與評價平台 API 運行中"}
