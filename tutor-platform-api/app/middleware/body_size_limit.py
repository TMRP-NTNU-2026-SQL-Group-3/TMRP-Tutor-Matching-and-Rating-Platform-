import logging

logger = logging.getLogger("app.body_size")


class _BodyTooLargeError(Exception):
    pass


class BodySizeLimitMiddleware:
    """Reject oversized request bodies at the HTTP edge.

    MEDIUM-1: Content-Length alone is insufficient because HTTP/1.1 clients
    can send `Transfer-Encoding: chunked` with no Content-Length header. We
    therefore run as a pure ASGI middleware, inspect Content-Length first
    for the fast-reject path, and otherwise wrap `receive` to count bytes
    streaming in, short-circuiting the app as soon as the cap is breached.
    """

    def __init__(self, app, max_bytes: int):
        self.app = app
        self._max = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = "-"
        for name, value in scope.get("headers", []):
            if name == b"x-request-id":
                try:
                    request_id = value.decode("latin-1")
                except Exception:
                    pass
                break

        # Fast path: trust a well-formed Content-Length when present.
        declared = None
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    declared = int(value.decode())
                except ValueError:
                    declared = -1
                break
        if declared is not None and declared > self._max:
            logger.warning(
                "rejected oversized body (Content-Length): %d > %d [request_id=%s]",
                declared, self._max, request_id,
            )
            await self._send_too_large(send)
            return

        max_bytes = self._max
        total = 0
        response_started = False

        async def wrapped_receive():
            nonlocal total
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"") or b""
                total += len(body)
                if total > max_bytes:
                    logger.warning(
                        "rejected oversized body (streamed): %d > %d [request_id=%s]",
                        total, max_bytes, request_id,
                    )
                    raise _BodyTooLargeError()
            return message

        async def wrapped_send(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, wrapped_receive, wrapped_send)
        except _BodyTooLargeError:
            if not response_started:
                await self._send_too_large(send)

    async def _send_too_large(self, send):
        import json
        mb = self._max // 1024 // 1024
        payload = json.dumps(
            {"success": False, "data": None,
             "message": f"請求內容過大（上限 {mb} MB）"},
            ensure_ascii=False,
        ).encode("utf-8")
        # I-10: BodySizeLimitMiddleware is registered after
        # SecurityHeadersMiddleware, which means in the request chain it sits
        # *outside* it — when we short-circuit here, the response never
        # traverses SecurityHeadersMiddleware on the way back out, so its
        # headers are missing. Attach the same set inline so 413 responses
        # cannot be framed/sniffed. Keep the set in sync with
        # SecurityHeadersMiddleware.
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(payload)).encode()),
                (b"x-content-type-options", b"nosniff"),
                (b"x-frame-options", b"DENY"),
                (b"referrer-policy", b"strict-origin-when-cross-origin"),
                (b"cache-control", b"no-store"),
            ],
        })
        await send({"type": "http.response.body", "body": payload})
