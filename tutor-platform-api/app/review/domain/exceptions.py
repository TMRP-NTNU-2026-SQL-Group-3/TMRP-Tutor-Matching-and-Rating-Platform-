from app.shared.domain.exceptions import ConflictError, DomainException, NotFoundError, PermissionDeniedError


class ReviewNotFoundError(NotFoundError):
    def __init__(self):
        super().__init__("找不到此評價")


class ReviewLockedError(DomainException):
    def __init__(self):
        super().__init__("評價已超過編輯期限，無法修改")


class DuplicateReviewError(ConflictError):
    def __init__(self):
        super().__init__("您已對此配對提交過同類型的評價")
