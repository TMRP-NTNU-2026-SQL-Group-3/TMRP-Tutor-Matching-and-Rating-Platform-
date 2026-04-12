from app.shared.domain.exceptions import DomainException, NotFoundError, PermissionDeniedError


class ConversationNotFoundError(NotFoundError):
    def __init__(self):
        super().__init__("找不到此對話")


class SelfConversationError(DomainException):
    def __init__(self):
        super().__init__("不能與自己建立對話")
