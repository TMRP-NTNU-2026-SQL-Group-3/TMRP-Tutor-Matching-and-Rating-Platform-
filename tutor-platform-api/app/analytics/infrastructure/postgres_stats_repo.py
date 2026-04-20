from app.shared.infrastructure.base_repository import BaseRepository


class PostgresStatsRepository(BaseRepository):

    def get_tutor_by_user(self, user_id: int) -> dict | None:
        return self.fetch_one("SELECT tutor_id FROM tutors WHERE user_id = %s", (user_id,))

    def income_summary(self, tutor_id: int, year: int, month: int) -> dict:
        # `missing_rate_count` surfaces sessions whose match has a NULL
        # hourly_rate — otherwise SUM(se.hours * m.hourly_rate) silently
        # drops those rows and the caller can't tell a legitimately low
        # income month from a data-integrity gap.
        return self.fetch_one(
            """SELECT COALESCE(SUM(se.hours), 0) AS total_hours,
                      COALESCE(SUM(se.hours * m.hourly_rate), 0) AS total_income,
                      COUNT(*) AS session_count,
                      COUNT(*) FILTER (WHERE m.hourly_rate IS NULL) AS missing_rate_count
               FROM sessions se INNER JOIN matches m ON se.match_id = m.match_id
               WHERE m.tutor_id = %s
                 AND EXTRACT(YEAR FROM se.session_date) = %s
                 AND EXTRACT(MONTH FROM se.session_date) = %s""",
            (tutor_id, year, month),
        )

    def income_breakdown(self, tutor_id: int, year: int, month: int) -> list[dict]:
        return self.fetch_all(
            """SELECT st.name AS student_name, sub.subject_name,
                      SUM(se.hours) AS hours, SUM(se.hours * m.hourly_rate) AS income
               FROM sessions se
               INNER JOIN matches m ON se.match_id = m.match_id
               INNER JOIN students st ON m.student_id = st.student_id
               INNER JOIN subjects sub ON m.subject_id = sub.subject_id
               WHERE m.tutor_id = %s
                 AND EXTRACT(YEAR FROM se.session_date) = %s
                 AND EXTRACT(MONTH FROM se.session_date) = %s
               GROUP BY st.name, sub.subject_name""",
            (tutor_id, year, month),
        )

    def expense_summary(self, parent_user_id: int, year: int, month: int) -> dict:
        # See income_summary: surface the NULL-rate row count so the
        # caller can distinguish low expense from missing rate data.
        return self.fetch_one(
            """SELECT COALESCE(SUM(se.hours), 0) AS total_hours,
                      COALESCE(SUM(se.hours * m.hourly_rate), 0) AS total_expense,
                      COUNT(*) AS session_count,
                      COUNT(*) FILTER (WHERE m.hourly_rate IS NULL) AS missing_rate_count
               FROM sessions se
               INNER JOIN matches m ON se.match_id = m.match_id
               INNER JOIN students st ON m.student_id = st.student_id
               WHERE st.parent_user_id = %s
                 AND EXTRACT(YEAR FROM se.session_date) = %s
                 AND EXTRACT(MONTH FROM se.session_date) = %s""",
            (parent_user_id, year, month),
        )

    def expense_breakdown(self, parent_user_id: int, year: int, month: int) -> list[dict]:
        return self.fetch_all(
            """SELECT u.display_name AS tutor_display_name, sub.subject_name,
                      st.name AS student_name, SUM(se.hours) AS hours,
                      SUM(se.hours * m.hourly_rate) AS expense
               FROM sessions se
               INNER JOIN matches m ON se.match_id = m.match_id
               INNER JOIN students st ON m.student_id = st.student_id
               INNER JOIN subjects sub ON m.subject_id = sub.subject_id
               INNER JOIN tutors t ON m.tutor_id = t.tutor_id
               INNER JOIN users u ON t.user_id = u.user_id
               WHERE st.parent_user_id = %s
                 AND EXTRACT(YEAR FROM se.session_date) = %s
                 AND EXTRACT(MONTH FROM se.session_date) = %s
               GROUP BY u.display_name, sub.subject_name, st.name""",
            (parent_user_id, year, month),
        )

    def get_student(self, student_id: int) -> dict | None:
        return self.fetch_one(
            "SELECT student_id, parent_user_id FROM students WHERE student_id = %s",
            (student_id,),
        )

    def get_active_match_for_tutor(self, student_id: int, tutor_user_id: int) -> dict | None:
        return self.fetch_one(
            """SELECT 1 FROM matches m INNER JOIN tutors t ON m.tutor_id = t.tutor_id
               WHERE m.student_id = %s AND t.user_id = %s AND m.status IN ('active', 'trial')""",
            (student_id, tutor_user_id),
        )

    def get_tutor_subject_ids_for_student(self, student_id: int, tutor_user_id: int) -> set[int]:
        rows = self.fetch_all(
            """SELECT m.subject_id FROM matches m INNER JOIN tutors t ON m.tutor_id = t.tutor_id
               WHERE m.student_id = %s AND t.user_id = %s AND m.status IN ('active', 'trial')""",
            (student_id, tutor_user_id),
        )
        return {r["subject_id"] for r in rows}

    def student_progress_by_subjects(self, student_id: int, subject_ids: set[int]) -> list[dict]:
        if not subject_ids:
            return []
        return self.fetch_all(
            """SELECT e.exam_id, e.exam_date, e.exam_type, e.score, sub.subject_name
                FROM exams e INNER JOIN subjects sub ON e.subject_id = sub.subject_id
                WHERE e.student_id = %s AND e.subject_id = ANY(%s)
                ORDER BY e.exam_date""",
            (student_id, list(subject_ids)),
        )

    def student_progress(self, student_id: int, subject_id: int | None = None) -> list[dict]:
        if subject_id is not None:
            return self.fetch_all(
                """SELECT e.exam_id, e.exam_date, e.exam_type, e.score, sub.subject_name
                   FROM exams e INNER JOIN subjects sub ON e.subject_id = sub.subject_id
                   WHERE e.student_id = %s AND e.subject_id = %s ORDER BY e.exam_date""",
                (student_id, subject_id),
            )
        return self.fetch_all(
            """SELECT e.exam_id, e.exam_date, e.exam_type, e.score, sub.subject_name
               FROM exams e INNER JOIN subjects sub ON e.subject_id = sub.subject_id
               WHERE e.student_id = %s ORDER BY e.exam_date""",
            (student_id,),
        )
