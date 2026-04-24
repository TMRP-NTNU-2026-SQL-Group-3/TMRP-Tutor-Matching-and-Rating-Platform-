"""Per-user in-flight request quota.

I-07: a single authenticated caller issuing many concurrent requests can
lease every DB pool slot (rate-limit SELECT + handler query + nested
transaction), starving other users. This middleware caps the number of
concurrent requests a single user_id may hold open at once. The limit is
per-worker in-memory — sharing across workers via Redis would be cleaner,
but per-worker is sufficient to bound the fraction of the pool any one
caller can occupy: each worker has its own db_pool_max slice.
"""

import logging
import threading

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.shared.infrastructure.config import settings
from app.shared.infrastructure.security import decode_access_token

logger = logging.getLogger("app.user_quota")


class UserConcurrencyQuotaMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_concurrent: int | None = None):
        super().__init__(app)
        self._max = max_concurrent or settings.db_per_user_quota
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def _identify(self, request) -> str | None:
        token = request.cookies.get("access_token")
        if not token:
            auth = request.headers.get("authorization", "")
            if auth.lower().startswith("bearer "):
                token = auth.split(" ", 1)[1].strip()
        if not token:
            return None
        payload = decode_access_token(token)
        if payload is None:
            return None
        sub = payload.get("sub")
        return str(sub) if sub is not None else None

    async def dispatch(self, request, call_next):
        user_id = self._identify(request)
        if user_id is None:
            return await call_next(request)

        with self._lock:
            current = self._counts.get(user_id, 0)
            if current >= self._max:
                logger.warning(
                    "user_quota: user_id=%s denied — %d concurrent requests (cap=%d) path=%s",
                    user_id, current, self._max, request.url.path,
                )
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": "1"},
                    content={
                        "success": False, "data": None,
                        "message": "同時進行中的請求過多，請稍後再試",
                    },
                )
            self._counts[user_id] = current + 1

        try:
            return await call_next(request)
        finally:
            with self._lock:
                remaining = self._counts.get(user_id, 1) - 1
                if remaining <= 0:
                    self._counts.pop(user_id, None)
                else:
                    self._counts[user_id] = remaining
