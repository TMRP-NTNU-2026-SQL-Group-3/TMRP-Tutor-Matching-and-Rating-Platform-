from app.shared.domain.exceptions import DomainException, NotFoundError, PermissionDeniedError


class ConversationNotFoundError(NotFoundError):
    def __init__(self):
        super().__init__("找不到此對話")


class SelfConversationError(DomainException):
    def __init__(self):
        super().__init__("不能與自己建立對話")


class TargetUserNotFoundError(NotFoundError):
    def __init__(self):
        super().__init__("找不到該使用者")


class EmptyMessageError(DomainException):
    def __init__(self):
        super().__init__("訊息內容不可為空")


class NotConversationParticipantError(PermissionDeniedError):
    def __init__(self, action: str = "查看"):
        super().__init__(f"無權{action}此對話")
