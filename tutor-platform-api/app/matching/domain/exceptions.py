from app.shared.domain.exceptions import ConflictError, DomainException, NotFoundError, PermissionDeniedError


class InvalidTransitionError(DomainException):
    pass


class MatchNotFoundError(NotFoundError):
    def __init__(self):
        super().__init__("找不到此配對")


class MatchPermissionDeniedError(PermissionDeniedError):
    pass


class StudentNotOwnedError(PermissionDeniedError):
    def __init__(self):
        super().__init__("此子女不屬於您")


class TutorNotFoundError(NotFoundError):
    def __init__(self):
        super().__init__("找不到此老師")


class SubjectNotTaughtError(DomainException):
    def __init__(self):
        super().__init__("此老師未提供此科目的教學")


class DuplicateMatchError(ConflictError):
    def __init__(self):
        super().__init__("已存在進行中的配對")


class CapacityExceededError(DomainException):
    def __init__(self):
        super().__init__("此老師已達收生上限")
