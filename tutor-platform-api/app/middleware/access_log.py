import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("app.access")


class AccessLogMiddleware(BaseHTTPMiddleware):
    """記錄每個請求的方法、路徑、狀態碼與耗時。"""

    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "request",
            extra={
                "request_id": getattr(request.state, "request_id", "-"),
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 1),
                "client_ip": request.client.host,
                "user_agent": request.headers.get("user-agent", "-"),
            },
        )
        return response
