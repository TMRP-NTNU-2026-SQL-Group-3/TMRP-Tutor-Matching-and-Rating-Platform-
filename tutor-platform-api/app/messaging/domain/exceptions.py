from app.shared.domain.exceptions import DomainException, NotFoundError, PermissionDeniedError


class ConversationNotFoundError(NotFoundError):
    def __init__(self):
        super().__init__("找不到此對話")


class SelfConversationError(DomainException):
    def __init__(self):
        super().__init__("不能與自己建立對話")


class ConversationNotAllowedError(PermissionDeniedError):
    """S-M3: single generic 403 for both "no such user" and "no prior match"
    so a caller cannot distinguish the two cases and enumerate user IDs via
    different HTTP status codes."""
    def __init__(self):
        super().__init__("無法建立對話")


class EmptyMessageError(DomainException):
    def __init__(self):
        super().__init__("訊息內容不可為空")


class NotConversationParticipantError(PermissionDeniedError):
    def __init__(self, action: str = "查看"):
        super().__init__(f"無權{action}此對話")


class InvalidBeforeIdError(NotFoundError):
    def __init__(self):
        super().__init__("指定的訊息 ID 不存在於此對話")
