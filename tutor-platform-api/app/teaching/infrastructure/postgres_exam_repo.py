from app.shared.infrastructure.base_repository import BaseRepository
from app.teaching.domain.ports import IExamRepository


class PostgresExamRepository(BaseRepository, IExamRepository):

    def get_student(self, student_id: int) -> dict | None:
        return self.fetch_one(
            "SELECT student_id, parent_user_id FROM students WHERE student_id = %s",
            (student_id,),
        )

    def get_active_match_for_tutor(self, student_id: int, tutor_user_id: int) -> dict | None:
        return self.fetch_one(
            """SELECT 1 FROM matches m
               INNER JOIN tutors t ON m.tutor_id = t.tutor_id
               WHERE m.student_id = %s AND t.user_id = %s
                 AND m.status IN ('active', 'trial')""",
            (student_id, tutor_user_id),
        )

    def get_active_match_for_tutor_subject(
        self, student_id: int, tutor_user_id: int, subject_id: int
    ) -> dict | None:
        return self.fetch_one(
            """SELECT 1 FROM matches m
               INNER JOIN tutors t ON m.tutor_id = t.tutor_id
               WHERE m.student_id = %s AND t.user_id = %s AND m.subject_id = %s
                 AND m.status IN ('active', 'trial')""",
            (student_id, tutor_user_id, subject_id),
        )

    def create(self, student_id, subject_id, added_by_user_id, exam_date,
               exam_type, score, visible_to_parent) -> int:
        return self.execute_returning_id(
            """INSERT INTO exams
                (student_id, subject_id, added_by_user_id, exam_date,
                 exam_type, score, visible_to_parent, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
               RETURNING exam_id""",
            (student_id, subject_id, added_by_user_id,
             exam_date, exam_type, score, visible_to_parent),
        )

    def get_by_id(self, exam_id: int) -> dict | None:
        return self.fetch_one("SELECT * FROM exams WHERE exam_id = %s", (exam_id,))

    ALLOWED_COLUMNS = {"exam_date", "exam_type", "score", "visible_to_parent"}

    def update(self, exam_id: int, updates: dict) -> None:
        self.safe_update("exams", "exam_id", exam_id, updates, self.ALLOWED_COLUMNS)

    def delete(self, exam_id: int) -> None:
        self.execute("DELETE FROM exams WHERE exam_id = %s", (exam_id,))

    def list_by_student_for_tutor(self, student_id: int, tutor_user_id: int) -> list[dict]:
        # DISTINCT prevents duplicates when the tutor has multiple active/trial
        # matches with this student on the same subject (e.g. after a retry).
        return self.fetch_all(
            """SELECT DISTINCT e.*, s.subject_name FROM exams e
               INNER JOIN subjects s ON e.subject_id = s.subject_id
               INNER JOIN matches m ON e.student_id = m.student_id AND e.subject_id = m.subject_id
               INNER JOIN tutors t ON m.tutor_id = t.tutor_id
               WHERE e.student_id = %s AND t.user_id = %s
                 AND m.status IN ('active', 'trial')
               ORDER BY e.exam_date DESC""",
            (student_id, tutor_user_id),
        )

    def list_by_student(self, student_id: int, parent_only: bool = False) -> list[dict]:
        if parent_only:
            return self.fetch_all(
                """SELECT e.*, s.subject_name FROM exams e
                   INNER JOIN subjects s ON e.subject_id = s.subject_id
                   WHERE e.student_id = %s AND e.visible_to_parent = TRUE
                   ORDER BY e.exam_date DESC""",
                (student_id,),
            )
        return self.fetch_all(
            """SELECT e.*, s.subject_name FROM exams e
               INNER JOIN subjects s ON e.subject_id = s.subject_id
               WHERE e.student_id = %s ORDER BY e.exam_date DESC""",
            (student_id,),
        )
