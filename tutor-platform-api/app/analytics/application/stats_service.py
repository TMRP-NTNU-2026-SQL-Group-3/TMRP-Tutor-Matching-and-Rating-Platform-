"""Application-layer orchestration for income/expense/progress analytics.

Centralises the numeric normalisation (Decimal → float) and the
resource-ownership checks for student-progress queries. The router should
only hand off role-gated inputs and shape the response envelope.
"""

from app.analytics.infrastructure.postgres_stats_repo import PostgresStatsRepository
from app.shared.domain.exceptions import NotFoundError


def _to_float(value) -> float:
    return float(value or 0)


def _to_int(value) -> int:
    return int(value or 0)


def _shape_period_report(
    *, year: int, month: int, summary: dict | None,
    breakdown: list[dict], amount_key: str,
) -> dict:
    """Normalise a monthly aggregate + breakdown from Decimal to JSON-safe floats.

    `amount_key` is "income" for tutors, "expense" for parents — the only thing
    that differs between the two reports.

    `missing_rate_count` is forwarded from the repo so the UI can surface
    sessions whose matching row has a NULL hourly_rate (otherwise the SUM
    would silently drop those rows and the caller cannot tell a low-earnings
    month apart from a data-integrity gap).
    """
    summary = summary or {
        "total_hours": 0, f"total_{amount_key}": 0,
        "session_count": 0, "missing_rate_count": 0,
    }
    for row in breakdown:
        row["hours"] = _to_float(row.get("hours"))
        row[amount_key] = _to_float(row.get(amount_key))
    return {
        "year": year, "month": month,
        "total_hours": _to_float(summary["total_hours"]),
        f"total_{amount_key}": _to_float(summary[f"total_{amount_key}"]),
        "session_count": _to_int(summary["session_count"]),
        "missing_rate_count": _to_int(summary.get("missing_rate_count")),
        "breakdown": breakdown,
    }


class StatsAppService:
    def __init__(self, repo: PostgresStatsRepository):
        self._repo = repo

    def income_stats(self, *, user_id: int, year: int, month: int, tz: str = "Asia/Taipei") -> dict:
        tutor = self._repo.get_tutor_by_user(user_id)
        if not tutor:
            return {
                "year": year, "month": month,
                "total_hours": 0, "total_income": 0,
                "session_count": 0, "missing_rate_count": 0, "breakdown": [],
            }
        tutor_id = tutor["tutor_id"]
        return _shape_period_report(
            year=year, month=month,
            summary=self._repo.income_summary(tutor_id, year, month, tz),
            breakdown=self._repo.income_breakdown(tutor_id, year, month, tz),
            amount_key="income",
        )

    def expense_stats(self, *, parent_user_id: int, year: int, month: int, tz: str = "Asia/Taipei") -> dict:
        return _shape_period_report(
            year=year, month=month,
            summary=self._repo.expense_summary(parent_user_id, year, month, tz),
            breakdown=self._repo.expense_breakdown(parent_user_id, year, month, tz),
            amount_key="expense",
        )

    def student_progress(
        self, *, student_id: int, user_id: int,
        is_admin: bool, subject_id: int | None,
    ) -> list[dict]:
        # MEDIUM-7: collapse "does not exist" and "not yours" into a single
        # generic not-found response. The previous branch distinguished the
        # two cases, which let a caller enumerate the students table by
        # probing IDs and watching for 404 vs. 403.
        _NOT_FOUND = NotFoundError("找不到此學生")
        student = self._repo.get_student(student_id)
        if not student:
            raise _NOT_FOUND

        is_parent = student["parent_user_id"] == user_id
        is_tutor = bool(self._repo.get_active_match_for_tutor(student_id, user_id))
        if not is_parent and not is_tutor and not is_admin:
            raise _NOT_FOUND

        # Tutors see only the subjects they currently teach this student.
        if is_tutor and not is_parent and not is_admin:
            tutor_subject_ids = self._repo.get_tutor_subject_ids_for_student(
                student_id, user_id
            )
            if subject_id is not None:
                if subject_id not in tutor_subject_ids:
                    # Same treatment for subject-scoped enumeration: a tutor
                    # must not be able to tell whether a subject exists for
                    # a student they don't teach.
                    raise _NOT_FOUND
                exams = self._repo.student_progress(student_id, subject_id)
            else:
                exams = self._repo.student_progress_by_subjects(
                    student_id, tutor_subject_ids
                )
        else:
            exams = self._repo.student_progress(student_id, subject_id)

        for row in exams:
            row["score"] = _to_float(row.get("score"))
        return exams
