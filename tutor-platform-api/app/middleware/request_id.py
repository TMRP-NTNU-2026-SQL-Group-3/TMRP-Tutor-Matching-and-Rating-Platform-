import re
import uuid

from starlette.types import ASGIApp, Receive, Scope, Send

_SAFE_REQUEST_ID_RE = re.compile(r"^[a-zA-Z0-9\-_]{1,64}$")


class RequestIDMiddleware:
    """Assigns a unique ID to each request for log correlation.

    Pure ASGI implementation — does not buffer the response body.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        raw = headers.get(b"x-request-id", b"").decode("latin-1")
        if raw and _SAFE_REQUEST_ID_RE.match(raw):
            request_id = raw
        else:
            request_id = str(uuid.uuid4())

        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message):
            if message["type"] == "http.response.start":
                # Replace any existing X-Request-ID so an upstream proxy that
                # also injects one cannot leave the response carrying two
                # different IDs (which would split log correlation chains).
                preserved = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != b"x-request-id"
                ]
                message = {
                    **message,
                    "headers": preserved
                    + [(b"x-request-id", request_id.encode("latin-1"))],
                }
            await send(message)

        await self.app(scope, receive, send_with_request_id)
