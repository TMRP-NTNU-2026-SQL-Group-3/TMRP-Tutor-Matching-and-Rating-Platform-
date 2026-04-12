from app.shared.domain.exceptions import DomainException, NotFoundError


class TutorNotFoundError(NotFoundError):
    def __init__(self):
        super().__init__("找不到老師資料")


class StudentNotFoundError(NotFoundError):
    def __init__(self):
        super().__init__("找不到此學生")


class SubjectNotFoundError(DomainException):
    def __init__(self, subject_id: int):
        super().__init__(f"科目 ID {subject_id} 不存在")
