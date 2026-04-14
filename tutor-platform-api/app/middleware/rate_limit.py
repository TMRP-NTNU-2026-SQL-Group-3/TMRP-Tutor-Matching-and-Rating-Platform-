import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("app.rate_limit")

# Per-path rate limit: (max requests, window seconds).
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/api/auth/login": (10, 60),
    "/api/auth/register": (5, 60),
    # L-01: dedicated cap for refresh. Without this, refresh falls back to the
    # `default` (60/min) bucket, which lets a stolen refresh token mint a new
    # access token once per second and bypass the login bucket entirely. The
    # RateLimitMiddleware records the hit before the handler runs, so failed
    # refresh attempts (invalid/revoked token) are also counted.
    "/api/auth/refresh": (20, 60),
    # H-04: reset is now a two-step flow; apply rate limits to both stages.
    # The confirm step is the destructive one, so it gets a tighter budget.
    "/api/admin/reset/request": (5, 3600),  # 5/hour
    "/api/admin/reset/confirm": (3, 3600),  # 3/hour
    "/api/admin/import-all": (5, 86400),    # 5/day
    "/api/admin/seed": (5, 3600),           # 5/hour
    "default": (60, 60),
}

# M-06: Paths that must fail CLOSED if the rate-limit DB is unreachable.
# Rationale: on these endpoints a fail-open posture turns a DB outage into
# an open door for credential stuffing / account enumeration / destructive
# admin actions. For all other endpoints we keep fail-open so a rate-limit
# outage cannot take the whole product down.
FAIL_CLOSED_PATHS: frozenset[str] = frozenset({
    "/api/auth/login",
    "/api/auth/register",
    "/api/admin/reset/request",
    "/api/admin/reset/confirm",
    "/api/admin/import-all",
    "/api/admin/seed",
})


_CLEANUP_INTERVAL = 300  # 每 5 分鐘清理一次過期紀錄


def check_and_record_bucket(
    bucket_key: str,
    max_attempts: int,
    window_seconds: int,
    *,
    fail_closed: bool = False,
) -> bool:
    """Synchronous count-and-insert; returns whether this request is allowed.

    Bug #12: persisted in PostgreSQL so multi-worker deployments share a
    single counter — prevents attackers from slipping under per-process
    in-memory limits.

    Public helper used both by ``RateLimitMiddleware`` (per path+IP bucket) and
    by endpoints that need an additional dimension — e.g. ``/api/auth/login``
    applies a per-username bucket so a distributed-IP brute force cannot stay
    under the per-IP cap indefinitely (H-03).

    M-06: ``fail_closed`` controls the failure mode when the counter DB is
    unreachable. Default False (fail-open) keeps the site usable when
    rate-limiting degrades. Callers guarding authentication or destructive
    admin actions pass True so an outage can't remove the brake.
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
        if fail_closed:
            logger.exception(
                "Rate limit DB error for bucket=%s; failing CLOSED (sensitive path)",
                bucket_key,
            )
            return False
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

        # Offload the synchronous psycopg2 call to the thread pool so we
        # don't block the event loop.
        fail_closed = path in FAIL_CLOSED_PATHS
        allowed = await asyncio.to_thread(
            check_and_record_bucket,
            bucket_key,
            max_attempts,
            window,
            fail_closed=fail_closed,
        )

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"success": False, "data": None, "message": "請求過於頻繁，請稍後再試"},
            )

        return await call_next(request)
