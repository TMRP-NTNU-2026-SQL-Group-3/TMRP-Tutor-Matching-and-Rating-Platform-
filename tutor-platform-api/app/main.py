import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.middleware.access_log import AccessLogMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routers import admin, auth, exams, matches, messages, reviews, sessions, stats, students, subjects, tutors
from app.routers import health
from app.utils.logger import setup_logger

logger = setup_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API Server 啟動")
    # JWT_SECRET_KEY 與 ADMIN_PASSWORD 預設值已由 config.py model_validator 硬性阻擋
    from app.database import init_pool, close_pool, get_connection, release_connection

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
        logger.error("資料庫初始化失敗: %s", e)
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
    version="0.1.0",
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
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# ─── 掛載路由 ───
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(tutors.router)
app.include_router(students.router)
app.include_router(subjects.router)
app.include_router(matches.router)
app.include_router(sessions.router)
app.include_router(exams.router)
app.include_router(reviews.router)
app.include_router(messages.router)
app.include_router(stats.router)
app.include_router(admin.router)


@app.get("/")
async def root():
    return {"message": "家教媒合與評價平台 API 運行中"}


