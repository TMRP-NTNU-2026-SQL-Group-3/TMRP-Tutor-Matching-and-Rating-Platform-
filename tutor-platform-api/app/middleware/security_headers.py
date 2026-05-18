from starlette.types import ASGIApp, Receive, Scope, Send


class SecurityHeadersMiddleware:
    """Attach security response headers to defend against common web attacks.

    Pure ASGI implementation — does not buffer the response body.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                extra = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"cache-control", b"no-store"),
                    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
                ]
                # Replace, don't append: a handler (or an upstream middleware)
                # may have already set one of these headers, and emitting the
                # same name twice leaves the browser to pick — which on some
                # combinations (notably CSP) collapses to the *most permissive*
                # value and silently weakens the policy we intended to enforce.
                override_names = {name for name, _ in extra}
                preserved = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() not in override_names
                ]
                message = {**message, "headers": preserved + extra}
            await send(message)

        await self.app(scope, receive, send_with_headers)
