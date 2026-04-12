from app.catalog.domain.ports import ITutorRepository
from app.shared.infrastructure.base_repository import BaseRepository
from app.shared.infrastructure.database_tx import transaction


class PostgresTutorRepository(BaseRepository, ITutorRepository):

    def search(self, subject_id: int | None = None, school: str | None = None) -> list[dict]:
        sql = """
            SELECT t.tutor_id, t.user_id, t.university, t.department,
                   t.grade_year, t.self_intro, t.max_students,
                   t.show_university, t.show_department, t.show_grade_year,
                   t.show_hourly_rate, t.show_subjects,
                   u.display_name
            FROM tutors t
            INNER JOIN users u ON t.user_id = u.user_id
        """
        conditions = []
        params = []
        if subject_id is not None:
            conditions.append(
                "t.tutor_id IN (SELECT ts.tutor_id FROM tutor_subjects ts WHERE ts.subject_id = %s)"
            )
            params.append(subject_id)
        if school:
            escaped = school.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append("t.university LIKE %s ESCAPE '\\'")
            params.append(f"%{escaped}%")
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY t.tutor_id DESC"
        return self.fetch_all(sql, tuple(params))

    def search_with_stats(
        self,
        subject_id: int | None = None,
        school: str | None = None,
        min_rate: float | None = None,
        max_rate: float | None = None,
        min_rating: float | None = None,
        sort_by: str = "rating",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        # Single-pass query: subjects/avg_rate/avg_rating/active_count are aggregated
        # in subqueries instead of issuing N+3 round-trips per tutor.
        order_clause = {
            "rate_asc": "avg_rate ASC NULLS LAST, tutor_id DESC",
            "newest": "tutor_id DESC",
        }.get(sort_by, "avg_rating DESC NULLS LAST, tutor_id DESC")

        conditions = []
        params: list = []
        if subject_id is not None:
            conditions.append(
                "t.tutor_id IN (SELECT ts.tutor_id FROM tutor_subjects ts WHERE ts.subject_id = %s)"
            )
            params.append(subject_id)
        if school:
            escaped = school.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append("t.university LIKE %s ESCAPE '\\'")
            params.append(f"%{escaped}%")
        where_sql = (" WHERE " + " AND ".join(conditions)) if conditions else ""

        having_parts = []
        having_params: list = []
        if min_rate is not None:
            having_parts.append("COALESCE(s_agg.avg_rate, 0) >= %s")
            having_params.append(min_rate)
        if max_rate is not None:
            having_parts.append("COALESCE(s_agg.avg_rate, 0) <= %s")
            having_params.append(max_rate)
        if min_rating is not None:
            having_parts.append(
                "COALESCE("
                "(COALESCE(r_agg.avg_r1,0)+COALESCE(r_agg.avg_r2,0)+COALESCE(r_agg.avg_r3,0)+COALESCE(r_agg.avg_r4,0))"
                " / NULLIF("
                "(CASE WHEN r_agg.avg_r1 IS NOT NULL THEN 1 ELSE 0 END"
                "+CASE WHEN r_agg.avg_r2 IS NOT NULL THEN 1 ELSE 0 END"
                "+CASE WHEN r_agg.avg_r3 IS NOT NULL THEN 1 ELSE 0 END"
                "+CASE WHEN r_agg.avg_r4 IS NOT NULL THEN 1 ELSE 0 END), 0)"
                ", 0) >= %s"
            )
            having_params.append(min_rating)
        filter_sql = (" AND " + " AND ".join(having_parts)) if having_parts else ""

        base_sql = f"""
            SELECT t.tutor_id, t.user_id, t.university, t.department,
                   t.grade_year, t.self_intro, t.max_students,
                   t.show_university, t.show_department, t.show_grade_year,
                   t.show_hourly_rate, t.show_subjects,
                   u.display_name,
                   COALESCE(s_agg.subjects, '[]'::json) AS subjects,
                   COALESCE(s_agg.avg_rate, 0) AS avg_rate,
                   COALESCE(
                     (COALESCE(r_agg.avg_r1,0)+COALESCE(r_agg.avg_r2,0)+COALESCE(r_agg.avg_r3,0)+COALESCE(r_agg.avg_r4,0))
                     / NULLIF(
                       (CASE WHEN r_agg.avg_r1 IS NOT NULL THEN 1 ELSE 0 END
                       +CASE WHEN r_agg.avg_r2 IS NOT NULL THEN 1 ELSE 0 END
                       +CASE WHEN r_agg.avg_r3 IS NOT NULL THEN 1 ELSE 0 END
                       +CASE WHEN r_agg.avg_r4 IS NOT NULL THEN 1 ELSE 0 END), 0)
                   , 0) AS avg_rating,
                   COALESCE(r_agg.review_count, 0) AS review_count,
                   COALESCE(a_agg.active_count, 0) AS active_student_count
            FROM tutors t
            INNER JOIN users u ON t.user_id = u.user_id
            LEFT JOIN (
                SELECT ts.tutor_id,
                       json_agg(json_build_object(
                           'subject_id', ts.subject_id,
                           'subject_name', s.subject_name,
                           'category', s.category,
                           'hourly_rate', ts.hourly_rate
                       )) AS subjects,
                       AVG(ts.hourly_rate) AS avg_rate
                FROM tutor_subjects ts
                INNER JOIN subjects s ON ts.subject_id = s.subject_id
                GROUP BY ts.tutor_id
            ) s_agg ON s_agg.tutor_id = t.tutor_id
            LEFT JOIN (
                SELECT m.tutor_id,
                       AVG(r.rating_1) AS avg_r1,
                       AVG(r.rating_2) AS avg_r2,
                       AVG(r.rating_3) AS avg_r3,
                       AVG(r.rating_4) AS avg_r4,
                       COUNT(*) AS review_count
                FROM reviews r
                INNER JOIN matches m ON r.match_id = m.match_id
                WHERE r.review_type = 'parent_to_tutor'
                GROUP BY m.tutor_id
            ) r_agg ON r_agg.tutor_id = t.tutor_id
            LEFT JOIN (
                SELECT tutor_id, COUNT(*) AS active_count
                FROM matches
                WHERE status IN ('active', 'trial')
                GROUP BY tutor_id
            ) a_agg ON a_agg.tutor_id = t.tutor_id
            {where_sql}
        """

        filtered_sql = f"SELECT * FROM ({base_sql}) f WHERE 1=1{filter_sql}"
        count_sql = f"SELECT COUNT(*) AS cnt FROM ({filtered_sql}) c"
        count_row = self.fetch_one(count_sql, tuple(params + having_params))
        total = count_row["cnt"] if count_row else 0

        page_sql = f"{filtered_sql} ORDER BY {order_clause} LIMIT %s OFFSET %s"
        offset = (page - 1) * page_size
        rows = self.fetch_all(page_sql, tuple(params + having_params + [page_size, offset]))
        return rows, total

    def find_by_id(self, tutor_id: int) -> dict | None:
        return self.fetch_one(
            """SELECT t.*, u.display_name, u.email, u.phone
               FROM tutors t INNER JOIN users u ON t.user_id = u.user_id
               WHERE t.tutor_id = %s""",
            (tutor_id,),
        )

    def find_by_user_id(self, user_id: int) -> dict | None:
        return self.fetch_one("SELECT * FROM tutors WHERE user_id = %s", (user_id,))

    def get_subjects(self, tutor_id: int) -> list[dict]:
        return self.fetch_all(
            """SELECT ts.subject_id, s.subject_name, s.category, ts.hourly_rate
               FROM tutor_subjects ts INNER JOIN subjects s ON ts.subject_id = s.subject_id
               WHERE ts.tutor_id = %s""",
            (tutor_id,),
        )

    def get_availability(self, tutor_id: int) -> list[dict]:
        return self.fetch_all(
            """SELECT availability_id, day_of_week, start_time, end_time
               FROM tutor_availability WHERE tutor_id = %s
               ORDER BY day_of_week, start_time""",
            (tutor_id,),
        )

    def get_avg_rating(self, tutor_id: int) -> dict | None:
        return self.fetch_one(
            """SELECT AVG(r.rating_1) AS avg_r1, AVG(r.rating_2) AS avg_r2,
                      AVG(r.rating_3) AS avg_r3, AVG(r.rating_4) AS avg_r4,
                      COUNT(*) AS review_count
               FROM reviews r INNER JOIN matches m ON r.match_id = m.match_id
               WHERE m.tutor_id = %s AND r.review_type = 'parent_to_tutor'""",
            (tutor_id,),
        )

    def get_active_student_count(self, tutor_id: int) -> int:
        row = self.fetch_one(
            "SELECT COUNT(*) AS cnt FROM matches WHERE tutor_id = %s AND status IN ('active', 'trial')",
            (tutor_id,),
        )
        return row["cnt"] if row else 0

    def replace_subjects(self, tutor_id: int, items: list[dict]) -> None:
        with transaction(self.conn):
            self.cursor.execute("DELETE FROM tutor_subjects WHERE tutor_id = %s", (tutor_id,))
            for item in items:
                self.cursor.execute(
                    "INSERT INTO tutor_subjects (tutor_id, subject_id, hourly_rate) VALUES (%s, %s, %s)",
                    (tutor_id, item["subject_id"], item["hourly_rate"]),
                )

    def replace_availability(self, tutor_id: int, slots: list[dict]) -> None:
        with transaction(self.conn):
            self.cursor.execute("DELETE FROM tutor_availability WHERE tutor_id = %s", (tutor_id,))
            for slot in slots:
                self.cursor.execute(
                    "INSERT INTO tutor_availability (tutor_id, day_of_week, start_time, end_time) VALUES (%s, %s, %s, %s)",
                    (tutor_id, slot["day_of_week"], slot["start_time"], slot["end_time"]),
                )

    VISIBILITY_COLUMNS = {"show_university", "show_department", "show_grade_year", "show_hourly_rate", "show_subjects"}
    PROFILE_COLUMNS = {"university", "department", "grade_year", "self_intro", "teaching_experience", "max_students",
                       "show_university", "show_department", "show_grade_year", "show_hourly_rate", "show_subjects"}

    def update_visibility(self, tutor_id: int, flags: dict) -> None:
        self.validate_columns(list(flags.keys()), self.VISIBILITY_COLUMNS)
        set_parts = [f"{col} = %s" for col in flags]
        params = list(flags.values()) + [tutor_id]
        if set_parts:
            self.execute(f"UPDATE tutors SET {', '.join(set_parts)} WHERE tutor_id = %s", tuple(params))

    def update_profile(self, tutor_id: int, **fields) -> None:
        self.validate_columns(list(fields.keys()), self.PROFILE_COLUMNS)
        set_parts = [f"{col} = %s" for col in fields]
        params = list(fields.values()) + [tutor_id]
        if set_parts:
            self.execute(f"UPDATE tutors SET {', '.join(set_parts)} WHERE tutor_id = %s", tuple(params))
