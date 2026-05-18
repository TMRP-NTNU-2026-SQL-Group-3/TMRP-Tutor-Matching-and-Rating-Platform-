import secrets

from starlette.types import ASGIApp, Receive, Scope, Send

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

_CSRF_EXEMPT_PATHS = frozenset({"/api/auth/login", "/api/auth/register"})

_REJECT_BODY = b'{"success":false,"data":null,"message":"CSRF token \\u7121\\u6548\\u6216\\u7f3a\\u5931"}'


def _parse_cookies(raw: bytes) -> dict[str, str]:
    result = {}
    for item in raw.decode("latin-1").split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            result[k.strip()] = v.strip()
    return result


class CSRFMiddleware:
    """Double-submit cookie CSRF protection (SEC-03).

    Pure ASGI implementation — does not buffer the response body.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        path = scope.get("path", "/").rstrip("/") or "/"
        if method in _SAFE_METHODS or path in _CSRF_EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        cookies = _parse_cookies(headers.get(b"cookie", b""))
        cookie_token = cookies.get("csrf_token", "")
        header_token = headers.get(b"x-csrf-token", b"").decode("latin-1")

        if (
            not cookie_token
            or not header_token
            or not secrets.compare_digest(cookie_token, header_token)
        ):
            await send({
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(_REJECT_BODY)).encode()),
                ],
            })
            await send({"type": "http.response.body", "body": _REJECT_BODY})
            return

        await self.app(scope, receive, send)
