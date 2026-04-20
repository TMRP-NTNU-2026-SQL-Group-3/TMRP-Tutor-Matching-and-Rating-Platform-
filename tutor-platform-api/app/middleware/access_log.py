import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("app.access")

# Long User-Agent strings (Electron, mobile WebViews, headless tools) trivially
# fingerprint clients and inflate log rows. 120 chars keeps the browser/version
# prefix that's actually useful for debugging while dropping the long suffixes.
_USER_AGENT_MAX_CHARS = 120


def _truncate_user_agent(ua: str) -> tuple[str, int, bool]:
    """Return (value_for_log, original_length, truncated_flag).

    Surface the original length and a boolean flag alongside the truncated
    value so log consumers can tell that truncation happened and by how
    much — silent truncation makes it impossible to distinguish a 121-char
    UA from a 10 KB one when investigating an incident.
    """
    original_len = len(ua)
    if original_len <= _USER_AGENT_MAX_CHARS:
        return ua, original_len, False
    return ua[:_USER_AGENT_MAX_CHARS] + "…", original_len, True


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Log each request's method, path, status, and duration."""

    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        ua_value, ua_original_len, ua_truncated = _truncate_user_agent(
            request.headers.get("user-agent", "-")
        )
        logger.info(
            "request",
            extra={
                "request_id": getattr(request.state, "request_id", "-"),
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 1),
                "client_ip": request.client.host,
                "user_agent": ua_value,
                "user_agent_len": ua_original_len,
                "user_agent_truncated": ua_truncated,
            },
        )
        return response
