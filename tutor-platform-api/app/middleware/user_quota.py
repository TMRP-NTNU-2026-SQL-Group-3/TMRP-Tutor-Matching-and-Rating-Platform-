"""Per-user in-flight request quota.

I-07: a single authenticated caller issuing many concurrent requests can
lease every DB pool slot (rate-limit SELECT + handler query + nested
transaction), starving other users. This middleware caps the number of
concurrent requests a single user_id may hold open at once. The limit is
per-worker in-memory — sharing across workers via Redis would be cleaner,
but per-worker is sufficient to bound the fraction of the pool any one
caller can occupy: each worker has its own db_pool_max slice.
"""

import json
import logging
import threading

from starlette.types import ASGIApp, Receive, Scope, Send

from app.shared.infrastructure.config import settings
from app.shared.infrastructure.security import decode_access_token

logger = logging.getLogger("app.user_quota")


def _parse_cookies(raw: bytes) -> dict[str, str]:
    result = {}
    for item in raw.decode("latin-1").split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            result[k.strip()] = v.strip()
    return result


class UserConcurrencyQuotaMiddleware:
    """Pure ASGI implementation — does not buffer the response body."""

    def __init__(self, app: ASGIApp, max_concurrent: int | None = None):
        self.app = app
        self._max = max_concurrent or settings.db_per_user_quota
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def _identify(self, scope: Scope) -> str | None:
        headers = dict(scope.get("headers", []))
        cookies = _parse_cookies(headers.get(b"cookie", b""))
        token = cookies.get("access_token")
        if not token:
            auth = headers.get(b"authorization", b"").decode("latin-1")
            if auth.lower().startswith("bearer "):
                token = auth.split(" ", 1)[1].strip()
        if not token:
            return None
        payload = decode_access_token(token)
        if payload is None:
            return None
        sub = payload.get("sub")
        return str(sub) if sub is not None else None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        user_id = self._identify(scope)
        if user_id is None:
            await self.app(scope, receive, send)
            return

        with self._lock:
            current = self._counts.get(user_id, 0)
            if current >= self._max:
                over_limit = True
            else:
                over_limit = False
                self._counts[user_id] = current + 1

        if over_limit:
            path = scope.get("path", "?")
            logger.warning(
                "user_quota: user_id=%s denied — %d concurrent requests (cap=%d) path=%s",
                user_id, current, self._max, path,
            )
            body = json.dumps({
                "success": False, "data": None,
                "message": "同時進行中的請求過多，請稍後再試",
            }).encode()
            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"retry-after", b"1"),
                    (b"content-length", str(len(body)).encode()),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return

        try:
            await self.app(scope, receive, send)
        finally:
            with self._lock:
                remaining = self._counts.get(user_id, 1) - 1
                if remaining <= 0:
                    self._counts.pop(user_id, None)
                else:
                    self._counts[user_id] = remaining
