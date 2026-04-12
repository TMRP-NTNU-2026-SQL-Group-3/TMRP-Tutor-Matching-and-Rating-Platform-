from .exceptions import TutorNotFoundError, SubjectNotFoundError
from .ports import ITutorRepository, IStudentRepository


class TutorService:
    def __init__(self, tutor_repo: ITutorRepository):
        self._repo = tutor_repo

    def apply_visibility(self, tutor: dict) -> dict:
        """根據老師的隱私設定，遮蔽不公開的欄位。"""
        if not tutor.get("show_university"):
            tutor.pop("university", None)
        if not tutor.get("show_department"):
            tutor.pop("department", None)
        if not tutor.get("show_grade_year"):
            tutor.pop("grade_year", None)
        for key in [k for k in tutor if k.startswith("show_")]:
            del tutor[key]
        return tutor
