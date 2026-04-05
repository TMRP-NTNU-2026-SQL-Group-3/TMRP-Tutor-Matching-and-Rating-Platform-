from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.exceptions import AppException, app_exception_handler
from app.routers import admin, auth, exams, matches, messages, reviews, sessions, stats, students, subjects, tutors
from app.utils.logger import setup_logger

logger = setup_logger()

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
]

app = FastAPI(
    title="家教媒合與評價平台 API",
    description="TMRP — Tutor Matching and Rating Platform\n\n"
    "提供家長搜尋家教、配對媒合、上課管理、三向評價等完整功能的 RESTful API。",
    version="0.1.0",
    openapi_tags=tags_metadata,
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
    if settings.jwt_secret_key == "change-me-in-production":
        logger.warning(
            "⚠️ JWT_SECRET_KEY 使用預設值！請在 .env 中設定安全的密鑰。"
            "正式環境務必更換，否則任何人都能偽造 Token。"
        )
    if settings.admin_password == "admin123":
        logger.warning(
            "⚠️ ADMIN_PASSWORD 使用預設值！請在 .env 中設定強密碼。"
        )
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
