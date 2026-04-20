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
        """Return a copy of `tutor` with non-public fields masked.

        Does **not** mutate the input: a shallow copy of the dict and a
        one-level copy of each `subjects` element are taken so nested `pop`
        calls cannot leak rate information back to the shared row that
        callers may pass along to logging, caching, or serialization.

        Honours: show_hourly_rate (per-subject rate), show_subjects (subjects
        list), show_university, show_department, show_grade_year. Removes
        all show_* flags from the resulting dict so they never leak to
        other users. PII (email/phone, active_student_count) is always
        stripped — see HIGH-1.
        """
        result = dict(tutor)
        subjects = list(result.get("subjects") or [])
        if not result.get("show_hourly_rate", True):
            subjects = [
                {k: v for k, v in s.items() if k != "hourly_rate"}
                if isinstance(s, dict) else s
                for s in subjects
            ]
        result["subjects"] = subjects if result.get("show_subjects", True) else []

        if not result.get("show_university"):
            result.pop("university", None)
        if not result.get("show_department"):
            result.pop("department", None)
        if not result.get("show_grade_year"):
            result.pop("grade_year", None)
        result.pop("active_student_count", None)
        result.pop("email", None)
        result.pop("phone", None)
        for key in [k for k in result if k.startswith("show_")]:
            del result[key]
        return result
