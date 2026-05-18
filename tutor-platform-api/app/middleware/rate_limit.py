import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("app.rate_limit")

RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/api/auth/login": (10, 60),
    "/api/auth/register": (5, 60),
    "/api/auth/password": (5, 60),
    "/api/auth/refresh": (20, 60),
    "/api/admin/reset/request": (5, 3600),
    "/api/admin/reset/confirm": (1, 604800),
    "/api/admin/import-all": (5, 86400),
    "/api/admin/seed": (5, 3600),
    "/health": (30, 60),
    "/api/subjects": (30, 60),
    "/api/tutors": (30, 60),
    "/api/auth/me": (10, 60),
    "/api/tutors/profile": (10, 60),
    "default": (60, 60),
}


def _get_rate_limit(path: str) -> tuple[int, int]:
    """Return (max_requests, window_seconds) for path using longest-prefix match."""
    if path in RATE_LIMITS:
        return RATE_LIMITS[path]
    match = max(
        (k for k in RATE_LIMITS if k != "default" and path.startswith(k)),
        key=len,
        default=None,
    )
    return RATE_LIMITS[match] if match else RATE_LIMITS["default"]


FAIL_CLOSED_PATHS: frozenset[str] = frozenset({
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/password",
    "/api/admin/reset/request",
    "/api/admin/reset/confirm",
    "/api/admin/import-all",
    "/api/admin/seed",
})

_UNSAFE_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_CLEANUP_INTERVAL = 300


def check_and_record_bucket(
    bucket_key: str,
    max_attempts: int,
    window_seconds: int,
    *,
    fail_closed: bool = False,
) -> bool:
    """Synchronous count-and-insert; returns whether this request is allowed.

    Public helper used both by ``RateLimitMiddleware`` (per path+IP bucket) and
    by endpoints that need an additional dimension — e.g. ``/api/auth/login``
    applies a per-username bucket (H-03).
    """
    from app.shared.infrastructure.database import _require_rl_pool
    pool_ref = None
    conn = None
    try:
        pool_ref = _require_rl_pool()
        conn = pool_ref.getconn()
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        with conn.cursor() as cur:
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
                "INSERT INTO rate_limit_hits (bucket_key, expires_at)"
                " VALUES (%s, NOW() + %s * INTERVAL '1 second')",
                (bucket_key, window_seconds),
            )
        conn.commit()
        return True
    except Exception:
        if conn is not None:
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
        if pool_ref is not None and conn is not None:
            pool_ref.putconn(conn)


async def run_periodic_cleanup(interval: int = _CLEANUP_INTERVAL) -> None:
    """Background task that cleans expired rate-limit records on a fixed schedule."""
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(_cleanup_expired)
        except Exception:
            logger.exception("Periodic rate-limit cleanup failed")


def _cleanup_expired() -> int:
    """Delete rate-limit records whose per-bucket expiry has passed."""
    from app.shared.infrastructure.database import _require_rl_pool
    pool_ref = None
    conn = None
    try:
        pool_ref = _require_rl_pool()
        conn = pool_ref.getconn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM rate_limit_hits WHERE expires_at < NOW()")
            deleted = cur.rowcount
        conn.commit()
        return deleted or 0
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.exception("Rate limit cleanup failed")
        return 0
    finally:
        if pool_ref is not None and conn is not None:
            pool_ref.putconn(conn)


class RateLimitMiddleware:
    """IP + path sliding-window rate limiter backed by PostgreSQL.

    Pure ASGI implementation — does not buffer the response body.
    """

    def __init__(self, app: ASGIApp):
        self.app = app
        self._last_cleanup = time.time()
        self._cleanup_lock = asyncio.Lock()

    async def _maybe_cleanup(self, now: float) -> None:
        if now - self._last_cleanup < _CLEANUP_INTERVAL:
            return
        async with self._cleanup_lock:
            if now - self._last_cleanup < _CLEANUP_INTERVAL:
                return
            try:
                await asyncio.to_thread(_cleanup_expired)
            except Exception:
                logger.exception("Inline rate-limit cleanup failed; will retry next interval")
            self._last_cleanup = now

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        ip = client[0] if client else "unknown"
        path = scope.get("path", "/")
        method = scope.get("method", "GET")
        max_attempts, window = _get_rate_limit(path)
        bucket_key = f"{path}|{ip}"
        now = time.time()

        await self._maybe_cleanup(now)

        fail_closed = path in FAIL_CLOSED_PATHS or method in _UNSAFE_METHODS
        allowed = await asyncio.to_thread(
            check_and_record_bucket,
            bucket_key,
            max_attempts,
            window,
            fail_closed=fail_closed,
        )

        if not allowed:
            logger.warning(
                "rate_limit: 429 path=%s method=%s ip=%s bucket=%s limit=%d/%ds",
                path, method, ip, bucket_key, max_attempts, window,
            )
            body = json.dumps({
                "success": False, "data": None,
                "message": "請求過於頻繁，請稍後再試",
            }).encode()
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"retry-after", str(window).encode()),
                    (b"content-length", str(len(body)).encode()),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)
