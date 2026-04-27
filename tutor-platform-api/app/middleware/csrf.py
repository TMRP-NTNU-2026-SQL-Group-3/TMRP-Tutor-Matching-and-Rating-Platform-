import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Login and register have no csrf_token cookie yet — the cookie is issued as
# part of the response, so the request itself cannot carry it.
_CSRF_EXEMPT_PATHS = frozenset({"/api/auth/login", "/api/auth/register"})


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie CSRF protection (SEC-03).

    For every mutating request not in _CSRF_EXEMPT_PATHS the value of the
    non-httpOnly `csrf_token` cookie must match the `X-CSRF-Token` request
    header.  The server never stores the token; cross-origin scripts cannot
    read a cookie set by a different origin, so a mismatch proves the request
    did not originate from the legitimate SPA.
    """

    async def dispatch(self, request, call_next):
        if request.method in _SAFE_METHODS or request.url.path in _CSRF_EXEMPT_PATHS:
            return await call_next(request)

        cookie_token = request.cookies.get("csrf_token", "")
        header_token = request.headers.get("x-csrf-token", "")

        if (
            not cookie_token
            or not header_token
            or not secrets.compare_digest(cookie_token, header_token)
        ):
            return JSONResponse(
                status_code=403,
                content={"success": False, "data": None, "message": "CSRF token 無效或缺失"},
            )

        return await call_next(request)
