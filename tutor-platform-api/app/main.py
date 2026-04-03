from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.exceptions import AppException, app_exception_handler
from app.routers import admin, auth, exams, matches, messages, reviews, sessions, stats, students, subjects, tutors
from app.utils.logger import setup_logger

logger = setup_logger()

app = FastAPI(
    title="家教媒合與評價平台 API",
    description="TMRP — Tutor Matching and Rating Platform",
    version="0.1.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 統一錯誤處理
app.add_exception_handler(AppException, app_exception_handler)

# 掛載路由
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


@app.on_event("startup")
async def startup_event():
    logger.info("API Server 啟動")
    try:
        from app.database import get_connection
        from app.init_db import ensure_admin_user

        conn = get_connection()
        try:
            ensure_admin_user(conn, settings)
        finally:
            conn.close()
        logger.info("管理員帳號檢查完成")
    except Exception as e:
        logger.error("管理員帳號建立失敗: %s", e)
