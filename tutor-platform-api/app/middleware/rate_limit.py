import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("app.rate_limit")

# 每個路徑的速率限制：(最大請求數, 時間窗口秒數)
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/api/auth/login": (10, 60),
    "/api/auth/register": (5, 60),
    "/api/admin/reset": (3, 3600),        # 3 次/小時
    "/api/admin/import-all": (5, 86400),  # 5 次/天
    "/api/admin/seed": (5, 3600),         # 5 次/小時
    "default": (60, 60),
}


_CLEANUP_INTERVAL = 300  # 每 5 分鐘清理一次過期紀錄


def _check_and_record(bucket_key: str, max_attempts: int, window_seconds: int) -> bool:
    """同步的 DB 查詢 + 寫入；回傳是否允許此次請求。

    Bug #12: 用 PostgreSQL 持久化計數，多 worker 部署時共享同一份計數，
    避免攻擊者繞過 in-memory 的單 process 限流。
    """
    from app.shared.infrastructure.database import _require_pool
    pool_ref = _require_pool()
    conn = pool_ref.getconn()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM rate_limit_hits WHERE bucket_key = %s AND hit_at >= %s",
                (bucket_key, cutoff),
            )
            count = cur.fetchone()[0]
            if count >= max_attempts:
                conn.rollback()
                return False
            cur.execute(
                "INSERT INTO rate_limit_hits (bucket_key) VALUES (%s)",
                (bucket_key,),
            )
        conn.commit()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        # DB 故障時 fail-open（避免限流故障導致整站停擺），但記錄錯誤供調查
        logger.exception("Rate limit DB error for bucket=%s; failing open", bucket_key)
        return True
    finally:
        pool_ref.putconn(conn)


def _cleanup_expired() -> int:
    """清除超過最長視窗的紀錄。"""
    from app.shared.infrastructure.database import _require_pool
    max_window = max(w for _, w in RATE_LIMITS.values())
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_window)
    pool_ref = _require_pool()
    conn = pool_ref.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM rate_limit_hits WHERE hit_at < %s", (cutoff,))
            deleted = cur.rowcount
        conn.commit()
        return deleted or 0
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.exception("Rate limit cleanup failed")
        return 0
    finally:
        pool_ref.putconn(conn)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    基於 IP + 路徑的滑動視窗速率限制（DB 持久化，支援多 worker）。

    Bug #12: 由 in-memory 計數改為 PostgreSQL 表 (rate_limit_hits)，
    確保 uvicorn --workers N 部署下各 worker 共享計數。
    每次請求一次小型 SELECT + INSERT；高流量站點可考慮改用 Redis。
    """

    def __init__(self, app):
        super().__init__(app)
        self._last_cleanup = time.time()
        self._cleanup_lock = asyncio.Lock()

    async def _maybe_cleanup(self, now: float) -> None:
        if now - self._last_cleanup < _CLEANUP_INTERVAL:
            return
        async with self._cleanup_lock:
            if now - self._last_cleanup < _CLEANUP_INTERVAL:
                return
            await asyncio.to_thread(_cleanup_expired)
            self._last_cleanup = now

    async def dispatch(self, request, call_next):
        ip = request.client.host if request.client else "unknown"
        path = request.url.path
        max_attempts, window = RATE_LIMITS.get(path, RATE_LIMITS["default"])
        bucket_key = f"{path}|{ip}"
        now = time.time()

        await self._maybe_cleanup(now)

        # 把同步的 psycopg2 呼叫丟到 thread pool，避免阻塞 event loop
        allowed = await asyncio.to_thread(_check_and_record, bucket_key, max_attempts, window)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"success": False, "data": None, "message": "請求過於頻繁，請稍後再試"},
            )

        return await call_next(request)
