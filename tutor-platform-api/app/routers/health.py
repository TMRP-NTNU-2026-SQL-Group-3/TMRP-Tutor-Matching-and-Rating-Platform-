import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.database import get_db
from app.utils.security import decode_access_token

logger = logging.getLogger("app.health")
router = APIRouter(tags=["health"])


def _get_optional_user(request: Request) -> Optional[dict]:
    """嘗試從 Authorization header 解析使用者，失敗時回傳 None（不阻擋請求）。"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return decode_access_token(auth[7:])
    return None


@router.get("/health", summary="健康檢查", description="檢查 API 狀態。已認證的管理員可查看資料庫連線詳情。")
def health_check(request: Request, conn=Depends(get_db)):
    user = _get_optional_user(request)
    is_admin = user and user.get("role") == "admin"

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        cursor.fetchone()
        if is_admin:
            return {"status": "healthy", "database": "connected"}
        return {"status": "ok"}
    except Exception:
        logger.exception("Health check failed")
        if is_admin:
            return JSONResponse(
                status_code=503,
                content={"status": "unhealthy", "database": "disconnected"},
            )
        return JSONResponse(
            status_code=503,
            content={"status": "error"},
        )
