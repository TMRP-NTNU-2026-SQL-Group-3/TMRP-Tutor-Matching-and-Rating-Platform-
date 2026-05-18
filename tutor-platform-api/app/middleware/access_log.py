import ipaddress
import logging
import time

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("app.access")

_USER_AGENT_MAX_CHARS = 120


def _pseudonymize_ip(ip: str) -> str:
    """Retain enough of the address for network-level debugging while dropping
    the host-identifying suffix (GDPR Art. 25 — data minimisation).

    IPv4: mask the last octet (→ /24 prefix).
    IPv6: mask the interface identifier, keep the /64 routing prefix.
    Uses ipaddress to handle compressed :: notation correctly.
    """
    try:
        addr = ipaddress.ip_address(ip)
        if isinstance(addr, ipaddress.IPv6Address):
            net = ipaddress.IPv6Network(f"{ip}/64", strict=False)
            return str(net.network_address) + "/64"
        parts = ip.split(".")
        return f"{parts[0]}.{parts[1]}.{parts[2]}.0"
    except ValueError:
        return ip


def _truncate_user_agent(ua: str) -> tuple[str, int, bool]:
    """Return (value_for_log, original_length, truncated_flag)."""
    original_len = len(ua)
    if original_len <= _USER_AGENT_MAX_CHARS:
        return ua, original_len, False
    return ua[:_USER_AGENT_MAX_CHARS] + "…", original_len, True


class AccessLogMiddleware:
    """Log each request's method, path, status, and duration.

    Pure ASGI implementation — does not buffer the response body.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000

            headers = dict(scope.get("headers", []))
            ua_raw = headers.get(b"user-agent", b"-").decode("latin-1", errors="replace")
            ua_value, ua_original_len, ua_truncated = _truncate_user_agent(ua_raw)

            request_id = scope.get("state", {}).get("request_id", "-")
            method = scope.get("method", "?")
            path = scope.get("path", "?")
            client = scope.get("client")
            client_ip = _pseudonymize_ip(client[0]) if client else "unknown"

            logger.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "status": status_code,
                    "duration_ms": round(duration_ms, 1),
                    "client_ip": client_ip,
                    "user_agent": ua_value,
                    "user_agent_len": ua_original_len,
                    "user_agent_truncated": ua_truncated,
                },
            )
