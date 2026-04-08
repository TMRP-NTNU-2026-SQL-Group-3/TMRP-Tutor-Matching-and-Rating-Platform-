import asyncio
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# 每個路徑的速率限制：(最大請求數, 時間窗口秒數)
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/api/auth/login": (10, 60),
    "/api/auth/register": (5, 60),
    "/api/admin/reset": (3, 3600),        # 3 次/小時
    "/api/admin/import-all": (5, 86400),  # 5 次/天
    "/api/admin/seed": (5, 3600),         # 5 次/小時
    "default": (60, 60),
}


_CLEANUP_INTERVAL = 300  # 每 5 分鐘全域清理一次


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    基於 IP 的滑動視窗速率限制。

    ⚠️ 限制：使用 in-memory 計數器，僅在單 process 部署下有效。
    多 Worker (uvicorn --workers N) 部署時，各 process 維護獨立計數器，
    攻擊者可繞過限制。生產環境應改用 Redis 或資料庫持久化計數。
    """

    def __init__(self, app):
        super().__init__(app)
        self.attempts: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last_cleanup = time.time()
        self._cleanup_lock = asyncio.Lock()

    async def _periodic_cleanup(self, now: float):
        """定時清理所有路徑下的過期 bucket，避免記憶體洩漏。"""
        if now - self._last_cleanup < _CLEANUP_INTERVAL:
            return
        async with self._cleanup_lock:
            if now - self._last_cleanup < _CLEANUP_INTERVAL:
                return
            for path, buckets in list(self.attempts.items()):
                _, window = RATE_LIMITS.get(path, RATE_LIMITS["default"])
                stale = [k for k, v in buckets.items()
                         if not v or all(now - t >= window for t in v)]
                for k in stale:
                    del buckets[k]
                if not buckets:
                    del self.attempts[path]
            # 同時清理不再使用的 lock
            active_keys = {f"{p}:{ip}" for p, bs in self.attempts.items() for ip in bs}
            stale_locks = [k for k in self._locks if k not in active_keys]
            for k in stale_locks:
                del self._locks[k]
            self._last_cleanup = now

    async def dispatch(self, request, call_next):
        ip = request.client.host
        path = request.url.path
        max_attempts, window = RATE_LIMITS.get(path, RATE_LIMITS["default"])
        lock_key = f"{path}:{ip}"
        now = time.time()

        # 定時全域清理
        await self._periodic_cleanup(now)

        async with self._locks[lock_key]:
            now = time.time()

            bucket = self.attempts[path][ip]
            # 清除過期紀錄
            bucket[:] = [t for t in bucket if now - t < window]

            if len(bucket) >= max_attempts:
                return JSONResponse(
                    status_code=429,
                    content={"success": False, "data": None, "message": "請求過於頻繁，請稍後再試"},
                )
            bucket.append(now)

        return await call_next(request)
