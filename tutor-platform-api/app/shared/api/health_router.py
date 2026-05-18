import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.shared.infrastructure.database import get_db

logger = logging.getLogger("app.health")
router = APIRouter(tags=["health"])


@router.get("/health", summary="健康檢查", description="檢查 API 與資料庫連線狀態。")
def health_check(conn=Depends(get_db)):
    # Intentionally reveals DB reachability via 200/503 so load balancers and
    # orchestrators can drain the instance when the DB is unreachable. The
    # endpoint is rate-limited (30 req/min) to bound information-leakage risk.
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
