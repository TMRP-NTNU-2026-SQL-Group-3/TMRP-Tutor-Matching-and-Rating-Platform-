from app.database_tx import transaction
from app.repositories.base import BaseRepository
from app.utils.access_bits import to_access_bit


class TutorRepository(BaseRepository):

    def search(
        self,
        subject_id: int | None = None,
        school: str | None = None,
    ) -> list[dict]:
        sql = """
            SELECT t.tutor_id, t.user_id, t.university, t.department,
                   t.grade_year, t.self_intro, t.max_students,
                   t.show_university, t.show_department, t.show_grade_year,
                   t.show_hourly_rate, t.show_subjects,
                   u.display_name
            FROM Tutors t
            INNER JOIN Users u ON t.user_id = u.user_id
        """
        conditions = []
        params = []

        if subject_id is not None:
            conditions.append(
                "t.tutor_id IN (SELECT ts.tutor_id FROM Tutor_Subjects ts WHERE ts.subject_id = ?)"
            )
            params.append(subject_id)

        if school:
            escaped = school.replace("%", "[%]").replace("_", "[_]")
            conditions.append("t.university LIKE ?")
            params.append(f"%{escaped}%")

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        sql += " ORDER BY t.tutor_id DESC"
        return self.fetch_all(sql, tuple(params))

    def find_by_id(self, tutor_id: int) -> dict | None:
        sql = """
            SELECT t.*, u.display_name, u.email, u.phone
            FROM Tutors t
            INNER JOIN Users u ON t.user_id = u.user_id
            WHERE t.tutor_id = ?
        """
        return self.fetch_one(sql, (tutor_id,))

    def find_by_user_id(self, user_id: int) -> dict | None:
        sql = "SELECT * FROM Tutors WHERE user_id = ?"
        return self.fetch_one(sql, (user_id,))

    def get_subjects(self, tutor_id: int) -> list[dict]:
        sql = """
            SELECT ts.subject_id, s.subject_name, s.category, ts.hourly_rate
            FROM Tutor_Subjects ts
            INNER JOIN Subjects s ON ts.subject_id = s.subject_id
            WHERE ts.tutor_id = ?
        """
        return self.fetch_all(sql, (tutor_id,))

    def get_availability(self, tutor_id: int) -> list[dict]:
        sql = """
            SELECT availability_id, day_of_week, start_time, end_time
            FROM Tutor_Availability
            WHERE tutor_id = ?
            ORDER BY day_of_week, start_time
        """
        return self.fetch_all(sql, (tutor_id,))

    def get_avg_rating(self, tutor_id: int) -> dict | None:
        sql = """
            SELECT AVG(r.rating_1) AS avg_r1, AVG(r.rating_2) AS avg_r2,
                   AVG(r.rating_3) AS avg_r3, AVG(r.rating_4) AS avg_r4,
                   COUNT(*) AS review_count
            FROM Reviews r
            INNER JOIN Matches m ON r.match_id = m.match_id
            WHERE m.tutor_id = ? AND r.review_type = 'parent_to_tutor'
        """
        return self.fetch_one(sql, (tutor_id,))

    def get_active_student_count(self, tutor_id: int) -> int:
        sql = """
            SELECT COUNT(*) AS cnt FROM Matches
            WHERE tutor_id = ? AND status IN ('active', 'trial')
        """
        row = self.fetch_one(sql, (tutor_id,))
        return row["cnt"] if row else 0

    def replace_subjects(self, tutor_id: int, items: list[dict]) -> None:
        """整批替換老師的可教授科目（交易隔離）。"""
        with transaction(self.conn):
            self.cursor.execute("DELETE FROM Tutor_Subjects WHERE tutor_id = ?", (tutor_id,))
            for item in items:
                self.cursor.execute(
                    """
                    INSERT INTO Tutor_Subjects (tutor_id, subject_id, hourly_rate)
                    VALUES (?, ?, ?)
                    """,
                    (tutor_id, item["subject_id"], item["hourly_rate"]),
                )

    def replace_availability(self, tutor_id: int, slots: list[dict]) -> None:
        """整批替換老師的可用時段（交易隔離）。"""
        with transaction(self.conn):
            self.cursor.execute("DELETE FROM Tutor_Availability WHERE tutor_id = ?", (tutor_id,))
            for slot in slots:
                self.cursor.execute(
                    """
                    INSERT INTO Tutor_Availability (tutor_id, day_of_week, start_time, end_time)
                    VALUES (?, ?, ?, ?)
                    """,
                    (tutor_id, slot["day_of_week"], slot["start_time"], slot["end_time"]),
                )

    VISIBILITY_COLUMNS = {
        "show_university", "show_department", "show_grade_year",
        "show_hourly_rate", "show_subjects",
    }

    PROFILE_COLUMNS = {
        "university", "department", "grade_year", "self_intro",
        "teaching_experience", "max_students",
        "show_university", "show_department", "show_grade_year",
        "show_hourly_rate", "show_subjects",
    }

    def update_visibility(self, tutor_id: int, flags: dict) -> None:
        self.validate_columns(list(flags.keys()), self.VISIBILITY_COLUMNS)
        set_parts = []
        params = []
        for col, val in flags.items():
            set_parts.append(f"{col} = ?")
            params.append(to_access_bit(val))
        if not set_parts:
            return
        sql = f"UPDATE Tutors SET {', '.join(set_parts)} WHERE tutor_id = ?"
        params.append(tutor_id)
        self.execute(sql, tuple(params))

    def update_profile(self, tutor_id: int, **fields) -> None:
        self.validate_columns(list(fields.keys()), self.PROFILE_COLUMNS)
        set_parts = []
        params = []
        for col, val in fields.items():
            set_parts.append(f"{col} = ?")
            if isinstance(val, bool):
                params.append(to_access_bit(val))
            else:
                params.append(val)
        if not set_parts:
            return
        sql = f"UPDATE Tutors SET {', '.join(set_parts)} WHERE tutor_id = ?"
        params.append(tutor_id)
        self.execute(sql, tuple(params))
