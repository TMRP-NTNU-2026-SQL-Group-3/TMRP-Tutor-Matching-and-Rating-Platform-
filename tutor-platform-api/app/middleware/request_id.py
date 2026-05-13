import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware

# Allowlist: alphanumeric characters, hyphens, and underscores, capped at 64 chars.
# Rejects any value containing CRLF, spaces, or other control characters that
# could be used for log injection or header splitting.
_SAFE_REQUEST_ID_RE = re.compile(r"^[a-zA-Z0-9\-_]{1,64}$")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assigns a unique ID to each request for log correlation."""

    async def dispatch(self, request, call_next):
        raw = request.headers.get("X-Request-ID", "")
        if raw and _SAFE_REQUEST_ID_RE.match(raw):
            request_id = raw
        else:
            request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
