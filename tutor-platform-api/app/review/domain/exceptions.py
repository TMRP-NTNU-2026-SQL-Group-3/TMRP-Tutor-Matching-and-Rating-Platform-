from app.shared.domain.exceptions import ConflictError, DomainException, NotFoundError, PermissionDeniedError


class ReviewNotFoundError(NotFoundError):
    def __init__(self):
        super().__init__("找不到此評價")


class ReviewMatchNotFoundError(NotFoundError):
    def __init__(self):
        super().__init__("找不到此配對")


class ReviewLockedError(ConflictError):
    def __init__(self):
        super().__init__("評價已超過編輯期限，無法修改")


class DuplicateReviewError(ConflictError):
    def __init__(self):
        super().__init__("您已對此配對提交過同類型的評價")


class InvalidReviewTypeError(DomainException):
    def __init__(self):
        super().__init__("評價類型必須為 parent_to_tutor、tutor_to_parent 或 tutor_to_student")


class MatchNotReviewableError(DomainException):
    def __init__(self):
        super().__init__("只能對進行中、暫停或已結束的配對提交評價")


class WrongReviewerRoleError(PermissionDeniedError):
    def __init__(self, review_type: str):
        if review_type == "parent_to_tutor":
            super().__init__("只有家長可以評價老師")
        else:
            super().__init__("只有老師可以評價家長或學生")


class NotReviewOwnerError(PermissionDeniedError):
    def __init__(self):
        super().__init__("只有評價者本人可以修改評價")


class NotMatchParticipantError(PermissionDeniedError):
    def __init__(self):
        super().__init__("無權查看此配對的評價")


class MatchHasNoSessionsError(DomainException):
    def __init__(self):
        super().__init__("尚無教學紀錄，請在至少一次課程後再提交評價")


class SelfReviewError(PermissionDeniedError):
    def __init__(self):
        super().__init__("評價者與被評價者不可為同一人")


class LowRatingCommentRequiredError(DomainException):
    def __init__(self, threshold: int, min_len: int):
        super().__init__(
            f"評分 {threshold} 星以下時必須填寫至少 {min_len} 字的文字說明",
            status_code=422,
        )


class MandatoryRatingAxisError(DomainException):
    def __init__(self):
        super().__init__("家長對老師的評價必須保留全部 4 項評分，不可設為 null", status_code=422)
