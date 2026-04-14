"""所有 Domain 例外的基底與共用子類別。"""


class DomainException(Exception):
    """所有 Domain 例外的基底"""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code


class NotFoundError(DomainException):
    def __init__(self, message: str = "資源不存在"):
        super().__init__(message, 404)


class PermissionDeniedError(DomainException):
    def __init__(self, message: str = "無權限執行此操作"):
        super().__init__(message, 403)


class ConflictError(DomainException):
    def __init__(self, message: str = "資源狀態衝突"):
        super().__init__(message, 409)


class TooManyRequestsError(DomainException):
    def __init__(self, message: str = "請求過於頻繁，請稍後再試"):
        super().__init__(message, 429)
