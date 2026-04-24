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
    # /health is probed by the docker healthcheck every 10s (6/min per
    # container) and by external uptime checks. It also runs a SELECT 1
    # against the DB — leaving it on the `default` bucket means an anonymous
    # caller can sustain 60 req/s of DB round-trips. Cap at a budget that
    # comfortably covers legitimate probes (docker + 1–2 external monitors)
    # but starves amplification attempts.
    "/health": (30, 60),
    "default": (60, 60),
}

# M-06: Paths that must fail CLOSED if the rate-limit DB is unreachable.
# Rationale: on these endpoints a fail-open posture turns a DB outage into
# an open door for credential stuffing / account enumeration / destructive
# admin actions. For safe-method endpoints we keep fail-open so a rate-limit
# outage cannot take read-only browsing of the whole product down.
FAIL_CLOSED_PATHS: frozenset[str] = frozenset({
    "/api/auth/login",
    "/api/auth/register",
    "/api/admin/reset/request",
    "/api/admin/reset/confirm",
    "/api/admin/import-all",
    "/api/admin/seed",
})

# HTTP methods whose requests change server state. These fail CLOSED by
# default even if the path is not in FAIL_CLOSED_PATHS — a rate-limit DB
# outage must not silently lift the brake on writes (match creation, review
# submission, message sending, etc.). Safe methods (GET/HEAD/OPTIONS) still
# fail open so read traffic can keep flowing during partial degradation.
_UNSAFE_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})


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
            # B3: The previous count-then-insert was racy — two concurrent
            # requests could each SELECT below the limit before either's
            # INSERT landed, letting both through. We serialize the
            # check+insert per bucket with a transaction-scoped advisory
            # lock keyed on hashtext(bucket_key); that way distinct buckets
            # still run in parallel, but a single bucket is effectively
            # single-threaded for the duration of this short critical
            # section. The lock is released automatically on COMMIT/ROLLBACK.
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (bucket_key,))
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


async def run_periodic_cleanup(interval: int = _CLEANUP_INTERVAL) -> None:
    """Background task that cleans expired rate-limit records on a fixed
    schedule, independent of request traffic."""
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(_cleanup_expired)
        except Exception:
            logger.exception("Periodic rate-limit cleanup failed")


def _cleanup_expired() -> int:
    """Delete rate-limit records older than the longest configured window."""
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
        fail_closed = path in FAIL_CLOSED_PATHS or request.method in _UNSAFE_METHODS
        allowed = await asyncio.to_thread(
            check_and_record_bucket,
            bucket_key,
            max_attempts,
            window,
            fail_closed=fail_closed,
        )

        if not allowed:
            # I-09: emit a log line for every 429 so SOC tooling / log search
            # can surface brute-force and scraping patterns. We deliberately
            # log IP + path + method only — no request body, no user_id —
            # so the signal is useful without becoming a PII sink.
            logger.warning(
                "rate_limit: 429 path=%s method=%s ip=%s bucket=%s limit=%d/%ds",
                path, request.method, ip, bucket_key, max_attempts, window,
            )
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(window)},
                content={"success": False, "data": None, "message": "請求過於頻繁，請稍後再試"},
            )

        return await call_next(request)
