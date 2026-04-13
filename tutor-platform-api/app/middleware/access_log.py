import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("app.access")

# Long User-Agent strings (Electron, mobile WebViews, headless tools) trivially
# fingerprint clients and inflate log rows. 120 chars keeps the browser/version
# prefix that's actually useful for debugging while dropping the long suffixes.
_USER_AGENT_MAX_CHARS = 120


def _truncate_user_agent(ua: str) -> str:
    if len(ua) <= _USER_AGENT_MAX_CHARS:
        return ua
    return ua[:_USER_AGENT_MAX_CHARS] + "…"


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
                "user_agent": _truncate_user_agent(request.headers.get("user-agent", "-")),
            },
        )
        return response
