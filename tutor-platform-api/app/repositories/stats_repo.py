from app.repositories.base import BaseRepository


class StatsRepository(BaseRepository):

    def get_tutor_by_user(self, user_id: int) -> dict | None:
        return self.fetch_one(
            "SELECT tutor_id FROM Tutors WHERE user_id = ?",
            (user_id,),
        )

    def income_summary(self, tutor_id: int, year: int, month: int) -> dict:
        return self.fetch_one(
            """
            SELECT
                IIF(SUM(se.hours) IS NULL, 0, SUM(se.hours)) AS total_hours,
                IIF(SUM(se.hours * m.hourly_rate) IS NULL, 0, SUM(se.hours * m.hourly_rate)) AS total_income,
                COUNT(*) AS session_count
            FROM Sessions se
            INNER JOIN Matches m ON se.match_id = m.match_id
            WHERE m.tutor_id = ?
              AND YEAR(se.session_date) = ?
              AND MONTH(se.session_date) = ?
            """,
            (tutor_id, year, month),
        )

    def income_breakdown(self, tutor_id: int, year: int, month: int) -> list[dict]:
        return self.fetch_all(
            """
            SELECT
                st.name AS student_name,
                sub.subject_name,
                SUM(se.hours) AS hours,
                SUM(se.hours * m.hourly_rate) AS income
            FROM ((Sessions se
            INNER JOIN Matches m ON se.match_id = m.match_id)
            INNER JOIN Students st ON m.student_id = st.student_id)
            INNER JOIN Subjects sub ON m.subject_id = sub.subject_id
            WHERE m.tutor_id = ?
              AND YEAR(se.session_date) = ?
              AND MONTH(se.session_date) = ?
            GROUP BY st.name, sub.subject_name
            """,
            (tutor_id, year, month),
        )

    def expense_summary(self, parent_user_id: int, year: int, month: int) -> dict:
        return self.fetch_one(
            """
            SELECT
                IIF(SUM(se.hours) IS NULL, 0, SUM(se.hours)) AS total_hours,
                IIF(SUM(se.hours * m.hourly_rate) IS NULL, 0, SUM(se.hours * m.hourly_rate)) AS total_expense,
                COUNT(*) AS session_count
            FROM (Sessions se
            INNER JOIN Matches m ON se.match_id = m.match_id)
            INNER JOIN Students st ON m.student_id = st.student_id
            WHERE st.parent_user_id = ?
              AND YEAR(se.session_date) = ?
              AND MONTH(se.session_date) = ?
            """,
            (parent_user_id, year, month),
        )

    def expense_breakdown(self, parent_user_id: int, year: int, month: int) -> list[dict]:
        return self.fetch_all(
            """
            SELECT
                u.display_name AS tutor_display_name,
                sub.subject_name,
                st.name AS student_name,
                SUM(se.hours) AS hours,
                SUM(se.hours * m.hourly_rate) AS expense
            FROM ((((Sessions se
            INNER JOIN Matches m ON se.match_id = m.match_id)
            INNER JOIN Students st ON m.student_id = st.student_id)
            INNER JOIN Subjects sub ON m.subject_id = sub.subject_id)
            INNER JOIN Tutors t ON m.tutor_id = t.tutor_id)
            INNER JOIN Users u ON t.user_id = u.user_id
            WHERE st.parent_user_id = ?
              AND YEAR(se.session_date) = ?
              AND MONTH(se.session_date) = ?
            GROUP BY u.display_name, sub.subject_name, st.name
            """,
            (parent_user_id, year, month),
        )

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

    def get_tutor_subject_ids_for_student(self, student_id: int, tutor_user_id: int) -> set[int]:
        """取得教師與此學生的進行中配對所涉及的科目 ID 集合。"""
        rows = self.fetch_all(
            """
            SELECT m.subject_id FROM Matches m
            INNER JOIN Tutors t ON m.tutor_id = t.tutor_id
            WHERE m.student_id = ? AND t.user_id = ?
              AND m.status IN ('active', 'trial')
            """,
            (student_id, tutor_user_id),
        )
        return {r["subject_id"] for r in rows}

    def student_progress_by_subjects(self, student_id: int, subject_ids: set[int]) -> list[dict]:
        """取得學生在指定科目集合中的歷次考試分數。"""
        if not subject_ids:
            return []
        placeholders = ", ".join("?" for _ in subject_ids)
        return self.fetch_all(
            f"""
            SELECT e.exam_id, e.exam_date, e.exam_type, e.score,
                   sub.subject_name
            FROM Exams e
            INNER JOIN Subjects sub ON e.subject_id = sub.subject_id
            WHERE e.student_id = ? AND e.subject_id IN ({placeholders})
            ORDER BY e.exam_date
            """,
            (student_id, *subject_ids),
        )

    def student_progress(self, student_id: int, subject_id: int | None = None) -> list[dict]:
        """取得學生歷次考試分數，可選按科目篩選。"""
        if subject_id is not None:
            return self.fetch_all(
                """
                SELECT e.exam_id, e.exam_date, e.exam_type, e.score,
                       sub.subject_name
                FROM Exams e
                INNER JOIN Subjects sub ON e.subject_id = sub.subject_id
                WHERE e.student_id = ? AND e.subject_id = ?
                ORDER BY e.exam_date
                """,
                (student_id, subject_id),
            )
        return self.fetch_all(
            """
            SELECT e.exam_id, e.exam_date, e.exam_type, e.score,
                   sub.subject_name
            FROM Exams e
            INNER JOIN Subjects sub ON e.subject_id = sub.subject_id
            WHERE e.student_id = ?
            ORDER BY e.exam_date
            """,
            (student_id,),
        )
