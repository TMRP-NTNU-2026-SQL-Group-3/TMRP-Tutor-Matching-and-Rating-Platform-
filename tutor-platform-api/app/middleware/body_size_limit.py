import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("app.body_size")


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Phase 4 A2: reject oversized request bodies at the HTTP edge.

    Enforces a hard cap via the Content-Length header so a hostile client
    cannot buffer a multi-GB payload into uvicorn before the route even
    runs. Admin CSV/ZIP uploads stay within the cap (see
    ``settings.admin_max_upload_bytes``); everything else is expected to
    fit in well under a megabyte.
    """

    def __init__(self, app, max_bytes: int):
        super().__init__(app)
        self._max = max_bytes

    async def dispatch(self, request, call_next):
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                length = int(cl)
            except ValueError:
                length = -1
            if length > self._max:
                request_id = getattr(request.state, "request_id", "-")
                logger.warning(
                    "rejected oversized body: %d bytes > %d limit [request_id=%s]",
                    length, self._max, request_id,
                )
                return JSONResponse(
                    status_code=413,
                    content={
                        "success": False,
                        "data": None,
                        "message": f"請求內容過大（上限 {self._max // 1024 // 1024} MB）",
                    },
                )
        return await call_next(request)
