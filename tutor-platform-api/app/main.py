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
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

# 各 BC 的 router
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


async def validation_exception_handler(request, exc: RequestValidationError):
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


async def http_exception_handler(request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "data": None, "message": exc.detail or "HTTP 錯誤"},
    )


async def unhandled_exception_handler(request, exc: Exception):
    # 帶上 RequestIDMiddleware 注入的 request_id，讓使用者回報的錯誤可對應到日誌
    request_id = getattr(request.state, "request_id", None)
    logger.exception(
        "Unhandled exception on %s %s [request_id=%s]: %s: %s",
        request.method, request.url.path, request_id, type(exc).__name__, exc,
    )
    body = {"success": False, "data": None, "message": "伺服器內部錯誤"}
    if request_id:
        body["request_id"] = request_id
    headers = {"X-Request-ID": request_id} if request_id else None
    return JSONResponse(status_code=500, content=body, headers=headers)


# Bug #17: 容器啟動順序 — 在資料庫 schema 初始化完成前不應通過 healthcheck，
# 否則 docker-compose 的 service_healthy 條件可能讓依賴服務（web）提前連線。
# 由於 init_pool + create_schema 均在 yield 之前同步完成，FastAPI 直到本協程 yield
# 才會開始接收請求；只要 docker healthcheck 的 start_period 大於初始化耗時即可。
# 已於 docker-compose.yml 設定 start_period=30s 涵蓋首次冷啟動。
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API Server 啟動")
    from app.shared.infrastructure.database import init_pool, close_pool, get_connection, release_connection

    init_pool()
    logger.info("PostgreSQL 連線池已建立")

    try:
        from app.init_db import create_schema, seed_subjects, ensure_admin_user

        conn = get_connection()
        try:
            create_schema(conn)
            seed_subjects(conn)
            ensure_admin_user(conn, settings)
        finally:
            release_connection(conn)
        logger.info("資料庫初始化與管理員帳號檢查完成")
    except Exception as e:
        # 初始化失敗時讓進程崩潰，避免帶著半初始化的狀態繼續服務請求
        logger.exception("資料庫初始化失敗，伺服器拒絕啟動: %s", e)
        raise
    yield
    # Shutdown
    close_pool()
    logger.info("API Server 關閉 — flushing logs")
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

app = FastAPI(
    title="家教媒合與評價平台 API",
    description="TMRP — Tutor Matching and Rating Platform\n\n"
    "提供家長搜尋家教、配對媒合、上課管理、三向評價等完整功能的 RESTful API。",
    version="0.2.0",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

# ─── Middleware（Starlette 最後註冊 = 最外層，請求由外往內穿透）───
# 5. Rate limiting（最靠近路由 → 最先註冊 → 最內層）
app.add_middleware(RateLimitMiddleware)
# 4. Access logging（需要 request_id，故在 RequestID 之內）
app.add_middleware(AccessLogMiddleware)
# 3. Security headers
app.add_middleware(SecurityHeadersMiddleware)
# 2. Request ID
app.add_middleware(RequestIDMiddleware)
# 1. CORS（最外層 — 最後註冊 → 最先執行，確保所有回應都帶 CORS 標頭）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# ─── 統一錯誤處理 ───
app.add_exception_handler(DomainException, domain_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# ─── 掛載路由 ───
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
