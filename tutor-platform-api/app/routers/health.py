import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.database import get_db

logger = logging.getLogger("app.health")
router = APIRouter(tags=["health"])


@router.get("/health", summary="健康檢查", description="檢查 API 與資料庫連線狀態。")
def health_check(conn=Depends(get_db)):
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM Users")
        cursor.fetchone()
        return {"status": "healthy", "database": "connected"}
    except Exception:
        logger.exception("Health check failed")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": "disconnected"},
        )
