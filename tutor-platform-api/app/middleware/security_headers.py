from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach security response headers to defend against common web attacks."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        # M-04: X-XSS-Protection is removed. Modern browsers (Chrome 78+,
        # Edge 17+, Firefox) no longer support the XSS auditor, and in legacy
        # IE the header has been implicated in introducing XSS bugs.
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        # S-H3: Content-Security-Policy. This is a JSON API; responses never
        # load scripts, styles, or frames. 'none' blocks all resource loading
        # and frame embedding. If the app later serves HTML (e.g. an admin UI),
        # tighten per-route instead of relaxing the global default.
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        # I-01: X-API-Version was previously hard-coded ("0.1.0") and drifted
        # from the FastAPI app version ("0.2.0") declared in main.py. Since
        # the header served no runtime purpose and leaked information useful
        # to CVE scanners, we stopped emitting it. Clients that need the
        # version can read it from /openapi.json when docs are enabled.
        return response
