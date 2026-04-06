import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# 每個路徑的速率限制：(最大請求數, 時間窗口秒數)
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/api/auth/login": (10, 60),
    "/api/auth/register": (5, 60),
    "default": (60, 60),
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    基於 IP 的滑動視窗速率限制。
    單一 process 部署適用；多 worker 需改用 Redis。
    """

    def __init__(self, app):
        super().__init__(app)
        self.attempts: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    async def dispatch(self, request, call_next):
        ip = request.client.host
        path = request.url.path
        max_attempts, window = RATE_LIMITS.get(path, RATE_LIMITS["default"])

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
