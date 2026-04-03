from fastapi import Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code


class NotFoundException(AppException):
    def __init__(self, message: str = "資源不存在"):
        super().__init__(message, 404)


class ForbiddenException(AppException):
    def __init__(self, message: str = "無權限執行此操作"):
        super().__init__(message, 403)


class ConflictException(AppException):
    def __init__(self, message: str = "資源狀態衝突"):
        super().__init__(message, 409)


async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "data": None, "message": exc.message},
    )
