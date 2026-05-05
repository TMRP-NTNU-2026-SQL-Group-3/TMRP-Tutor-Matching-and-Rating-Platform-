from app.shared.domain.exceptions import DomainException, NotFoundError, PermissionDeniedError
from app.teaching.domain.ports import IExamRepository


class ExamAppService:
    def __init__(self, repo: IExamRepository):
        self._repo = repo

    def create_exam(self, *, user_id: int, role: str, body) -> int:
        if role not in ("parent", "tutor"):
            raise DomainException("僅家長或老師可新增考試紀錄")
        student = self._repo.get_student(body.student_id)
        if not student:
            raise NotFoundError("找不到此學生")
        is_parent = role == "parent" and student["parent_user_id"] == user_id
        is_tutor = role == "tutor" and bool(
            self._repo.get_active_match_for_tutor_subject(body.student_id, user_id, body.subject_id)
        )
        if not is_parent and not is_tutor:
            raise PermissionDeniedError("無權為此學生新增考試紀錄")
        return self._repo.create(
            student_id=body.student_id,
            subject_id=body.subject_id,
            added_by_user_id=user_id,
            exam_date=body.exam_date,
            exam_type=body.exam_type,
            score=body.score,
            visible_to_parent=body.visible_to_parent,
        )

    def list_exams(self, *, user_id: int, role: str, student_id: int, is_admin: bool) -> list:
        student = self._repo.get_student(student_id)
        if not student:
            raise NotFoundError("找不到此學生")
        is_parent = student["parent_user_id"] == user_id
        # S-H6: use role to gate the tutor path — list_by_student_for_tutor enforces
        # subject-level access via JOIN on matches.subject_id, regardless of other
        # active matches for this student.
        is_tutor_role = role == "tutor"
        has_match = is_tutor_role and bool(self._repo.get_active_match_for_tutor(student_id, user_id))
        if not is_parent and not has_match and not is_admin:
            raise PermissionDeniedError("無權查看此學生的考試紀錄")
        if has_match and not is_parent and not is_admin:
            return self._repo.list_by_student_for_tutor(student_id, user_id)
        return self._repo.list_by_student(student_id, parent_only=is_parent and not is_admin)

    def delete_exam(self, *, exam_id: int, user_id: int) -> None:
        exam = self._repo.get_by_id(exam_id)
        # SEC-10: normalize ownership failure to 404 so sequential exam_id values
        # cannot be enumerated by comparing 403 vs 404 response codes.
        if not exam or exam["added_by_user_id"] != user_id:
            raise NotFoundError("找不到此考試紀錄")
        self._repo.delete(exam_id)

    def update_exam(self, *, exam_id: int, user_id: int, updates: dict) -> None:
        exam = self._repo.get_by_id(exam_id)
        # SEC-10: normalize ownership failure to 404.
        if not exam or exam["added_by_user_id"] != user_id:
            raise NotFoundError("找不到此考試紀錄")
        self._repo.update(exam_id, updates)
