from app.shared.domain.exceptions import DomainException, NotFoundError, PermissionDeniedError


class SessionNotFoundError(NotFoundError):
    def __init__(self):
        super().__init__("找不到此上課日誌")


class MatchNotActiveError(DomainException):
    def __init__(self):
        super().__init__("只有進行中或試教中的配對可以記錄上課日誌")


class ExamNotFoundError(NotFoundError):
    def __init__(self):
        super().__init__("找不到此考試紀錄")
