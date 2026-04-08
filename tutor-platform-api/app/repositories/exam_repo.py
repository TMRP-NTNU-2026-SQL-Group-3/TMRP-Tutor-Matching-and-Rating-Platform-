from app.repositories.base import BaseRepository
from app.utils.access_bits import to_access_bit


class ExamRepository(BaseRepository):

    def get_student(self, student_id: int) -> dict | None:
        return self.fetch_one(
            "SELECT student_id, parent_user_id FROM Students WHERE student_id = ?",
            (student_id,),
        )

    def get_active_match_for_tutor(self, student_id: int, tutor_user_id: int) -> dict | None:
        """確認老師目前有此學生的進行中配對。"""
        return self.fetch_one(
            """
            SELECT 1 FROM Matches m
            INNER JOIN Tutors t ON m.tutor_id = t.tutor_id
            WHERE m.student_id = ? AND t.user_id = ?
              AND m.status IN ('active', 'trial')
            """,
            (student_id, tutor_user_id),
        )

    def create(
        self, student_id: int, subject_id: int, added_by_user_id: int,
        exam_date, exam_type: str, score: float, visible_to_parent: bool,
    ) -> int:
        return self.execute_returning_id(
            """
            INSERT INTO Exams
                (student_id, subject_id, added_by_user_id, exam_date,
                 exam_type, score, visible_to_parent, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, Now())
            """,
            (
                student_id, subject_id, added_by_user_id,
                exam_date, exam_type, score,
                to_access_bit(visible_to_parent),
            ),
        )

    def get_by_id(self, exam_id: int) -> dict | None:
        return self.fetch_one(
            "SELECT * FROM Exams WHERE exam_id = ?",
            (exam_id,),
        )

    ALLOWED_COLUMNS = {"exam_date", "exam_type", "score", "visible_to_parent"}

    def update(self, exam_id: int, updates: dict) -> None:
        self.safe_update("Exams", "exam_id", exam_id, updates, self.ALLOWED_COLUMNS)

    def list_by_student(self, student_id: int, parent_only: bool = False) -> list[dict]:
        if parent_only:
            return self.fetch_all(
                """
                SELECT e.*, s.subject_name
                FROM Exams e
                INNER JOIN Subjects s ON e.subject_id = s.subject_id
                WHERE e.student_id = ? AND e.visible_to_parent <> 0
                ORDER BY e.exam_date DESC
                """,
                (student_id,),
            )
        return self.fetch_all(
            """
            SELECT e.*, s.subject_name
            FROM Exams e
            INNER JOIN Subjects s ON e.subject_id = s.subject_id
            WHERE e.student_id = ?
            ORDER BY e.exam_date DESC
            """,
            (student_id,),
        )
