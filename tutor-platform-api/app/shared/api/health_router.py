import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.shared.infrastructure.database import get_db

logger = logging.getLogger("app.health")
router = APIRouter(tags=["health"])


@router.get("/health", summary="健康檢查", description="檢查 API 與資料庫連線狀態。")
def health_check(conn=Depends(get_db)):
    # Return a uniform shape regardless of caller so the response cannot be
    # used to infer whether the caller is an admin.  Admin-only details
    # (database connectivity) are gated behind a separate admin endpoint.
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"status": "ok"}
    except Exception:
        logger.exception("Health check failed")
        return JSONResponse(
            status_code=503,
            content={"status": "error"},
        )
