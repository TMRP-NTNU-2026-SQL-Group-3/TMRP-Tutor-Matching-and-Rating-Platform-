from .exceptions import TutorNotFoundError, SubjectNotFoundError
from .ports import ITutorRepository, IStudentRepository


class TutorService:
    def __init__(self, tutor_repo: ITutorRepository):
        self._repo = tutor_repo

    def normalize_search_row(self, tutor: dict) -> dict:
        """Coerce optional numeric fields returned by the search query to stable types."""
        tutor["avg_rating"] = round(float(tutor.get("avg_rating") or 0), 2)
        tutor["review_count"] = int(tutor.get("review_count") or 0)
        return tutor

    def apply_visibility(self, tutor: dict) -> dict:
        """Mask non-public fields according to the tutor's privacy flags.

        Honours: show_hourly_rate (per-subject rate), show_subjects (subjects list),
        show_university, show_department, show_grade_year. Removes all show_*
        flags from the resulting dict so they never leak to other users.
        """
        subjects = tutor.get("subjects") or []
        if not tutor.get("show_hourly_rate", True):
            for s in subjects:
                if isinstance(s, dict):
                    s.pop("hourly_rate", None)
        tutor["subjects"] = subjects if tutor.get("show_subjects", True) else []

        if not tutor.get("show_university"):
            tutor.pop("university", None)
        if not tutor.get("show_department"):
            tutor.pop("department", None)
        if not tutor.get("show_grade_year"):
            tutor.pop("grade_year", None)
        for key in [k for k in tutor if k.startswith("show_")]:
            del tutor[key]
        return tutor
