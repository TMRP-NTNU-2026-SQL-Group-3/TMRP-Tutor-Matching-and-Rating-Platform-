from psycopg2 import sql as psql

from app.catalog.domain.ports import ITutorRepository
from app.shared.api.constants import DEFAULT_PAGE_SIZE
from app.shared.infrastructure.base_repository import BaseRepository, escape_like
from app.shared.infrastructure.column_validation import validate_columns
from app.shared.infrastructure.database_tx import transaction


class PostgresTutorRepository(BaseRepository, ITutorRepository):

    def search(self, subject_id: int | None = None, school: str | None = None) -> list[dict]:
        # B5: All dynamic SQL goes through psycopg2.sql.Composable so adding
        # a new filter later cannot accidentally reintroduce string
        # interpolation for an attacker-controlled value.
        base = psql.SQL("""
            SELECT t.tutor_id, t.user_id, t.university, t.department,
                   t.grade_year, t.self_intro, t.max_students,
                   t.show_university, t.show_department, t.show_grade_year,
                   t.show_hourly_rate, t.show_subjects,
                   u.display_name
            FROM tutors t
            INNER JOIN users u ON t.user_id = u.user_id
        """)
        conditions: list[psql.Composable] = []
        params: list = []
        if subject_id is not None:
            conditions.append(psql.SQL(
                "t.tutor_id IN (SELECT ts.tutor_id FROM tutor_subjects ts WHERE ts.subject_id = {})"
            ).format(psql.Placeholder()))
            params.append(subject_id)
        if school:
            escaped = escape_like(school)
            conditions.append(psql.SQL(
                "t.university LIKE {} ESCAPE '\\'"
            ).format(psql.Placeholder()))
            params.append(f"%{escaped}%")

        parts: list[psql.Composable] = [base]
        if conditions:
            parts.append(psql.SQL(" WHERE "))
            parts.append(psql.SQL(" AND ").join(conditions))
        parts.append(psql.SQL(" ORDER BY t.tutor_id DESC"))
        query = psql.Composed(parts).as_string(self.conn)
        return self.fetch_all(query, tuple(params))

    def search_with_stats(
        self,
        subject_id: int | None = None,
        school: str | None = None,
        min_rate: float | None = None,
        max_rate: float | None = None,
        min_rating: float | None = None,
        sort_by: str = "rating",
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[list[dict], int]:
        # Single-pass query: subjects/avg_rate/avg_rating/active_count are aggregated
        # in subqueries instead of issuing N+3 round-trips per tutor.
        # B5: sort_by is whitelisted via a fixed dict, so it is safe to
        # embed as a literal SQL fragment. Everything else is composed via
        # psycopg2.sql.
        _SORT_OPTIONS = {
            "rating": "avg_rating DESC NULLS LAST, tutor_id DESC",
            "rate_asc": "avg_rate ASC NULLS LAST, tutor_id DESC",
            "newest": "tutor_id DESC",
        }
        if sort_by not in _SORT_OPTIONS:
            raise ValueError(f"Unknown sort_by value: {sort_by!r}")
        order_clause = psql.SQL(_SORT_OPTIONS[sort_by])

        conditions: list[psql.Composable] = []
        params: list = []
        if subject_id is not None:
            conditions.append(psql.SQL(
                "t.tutor_id IN (SELECT ts.tutor_id FROM tutor_subjects ts WHERE ts.subject_id = {})"
            ).format(psql.Placeholder()))
            params.append(subject_id)
        if school:
            escaped = escape_like(school)
            conditions.append(psql.SQL(
                "t.university LIKE {} ESCAPE '\\'"
            ).format(psql.Placeholder()))
            params.append(f"%{escaped}%")
        where_sql = (
            psql.SQL(" WHERE ") + psql.SQL(" AND ").join(conditions)
            if conditions else psql.SQL("")
        )

        # Filters reference the inner query's output aliases (avg_rate,
        # avg_rating) rather than the subquery aliases, because `filter_sql`
        # is applied to the outer `SELECT * FROM (base_sql) f` wrapper.
        having_parts: list[psql.Composable] = []
        having_params: list = []
        if min_rate is not None:
            having_parts.append(psql.SQL("f.avg_rate >= {}").format(psql.Placeholder()))
            having_params.append(min_rate)
        if max_rate is not None:
            having_parts.append(psql.SQL("f.avg_rate <= {}").format(psql.Placeholder()))
            having_params.append(max_rate)
        if min_rating is not None:
            having_parts.append(psql.SQL("f.avg_rating >= {}").format(psql.Placeholder()))
            having_params.append(min_rating)
        filter_sql = (
            psql.SQL(" AND ") + psql.SQL(" AND ").join(having_parts)
            if having_parts else psql.SQL("")
        )

        # Rating / active-count aggregations come from v_tutor_ratings and
        # v_tutor_active_students (see init_db.py). Keeping them in the DB
        # prevents the same N-level subqueries from being re-inlined here
        # or in analytics.
        base_sql = psql.SQL("""
            SELECT t.tutor_id, t.user_id, t.university, t.department,
                   t.grade_year, t.self_intro, t.max_students,
                   t.show_university, t.show_department, t.show_grade_year,
                   t.show_hourly_rate, t.show_subjects,
                   u.display_name,
                   COALESCE(s_agg.subjects, '[]'::json) AS subjects,
                   COALESCE(s_agg.avg_rate, 0) AS avg_rate,
                   COALESCE(r_agg.avg_rating, 0) AS avg_rating,
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
            LEFT JOIN v_tutor_ratings r_agg ON r_agg.tutor_id = t.tutor_id
            LEFT JOIN v_tutor_active_students a_agg ON a_agg.tutor_id = t.tutor_id
            {where_sql}
        """).format(where_sql=where_sql)

        filtered_sql = psql.SQL("SELECT * FROM ({base}) f WHERE 1=1{filter}").format(
            base=base_sql, filter=filter_sql,
        )
        count_sql = psql.SQL("SELECT COUNT(*) AS cnt FROM ({inner}) c").format(inner=filtered_sql)
        count_row = self.fetch_one(count_sql.as_string(self.conn), tuple(params + having_params))
        total = count_row["cnt"] if count_row else 0

        page_sql = psql.SQL("{inner} ORDER BY {order} LIMIT {lim} OFFSET {off}").format(
            inner=filtered_sql,
            order=order_clause,
            lim=psql.Placeholder(),
            off=psql.Placeholder(),
        )
        offset = (page - 1) * page_size
        rows = self.fetch_all(
            page_sql.as_string(self.conn),
            tuple(params + having_params + [page_size, offset]),
        )
        return rows, total

    def find_by_id(self, tutor_id: int) -> dict | None:
        return self.fetch_one(
            """SELECT t.*, u.display_name, u.email, u.phone
               FROM tutors t INNER JOIN users u ON t.user_id = u.user_id
               WHERE t.tutor_id = %s""",
            (tutor_id,),
        )

    def find_detail(self, tutor_id: int) -> dict | None:
        """Single-query detail view: merges the tutor row with subjects,
        availability, rating aggregates, and active-student count.
        Replaces the previous 5-call N+1 pattern in the detail endpoint.
        COALESCE keeps shape stable for tutors with no reviews / empty
        subject or availability lists."""
        return self.fetch_one(
            """SELECT t.*, u.display_name, u.email, u.phone,
                      COALESCE(r.avg_r1, NULL) AS avg_r1,
                      COALESCE(r.avg_r2, NULL) AS avg_r2,
                      COALESCE(r.avg_r3, NULL) AS avg_r3,
                      COALESCE(r.avg_r4, NULL) AS avg_r4,
                      COALESCE(r.review_count, 0) AS review_count,
                      COALESCE(a.active_count, 0) AS active_student_count,
                      COALESCE(subj.subjects, '[]'::json) AS subjects,
                      COALESCE(avail.slots, '[]'::json) AS availability
               FROM tutors t
               INNER JOIN users u ON t.user_id = u.user_id
               LEFT JOIN v_tutor_ratings r ON r.tutor_id = t.tutor_id
               LEFT JOIN v_tutor_active_students a ON a.tutor_id = t.tutor_id
               LEFT JOIN LATERAL (
                   SELECT json_agg(json_build_object(
                       'subject_id', ts.subject_id,
                       'subject_name', s.subject_name,
                       'category', s.category,
                       'hourly_rate', ts.hourly_rate
                   )) AS subjects
                   FROM tutor_subjects ts
                   INNER JOIN subjects s ON ts.subject_id = s.subject_id
                   WHERE ts.tutor_id = t.tutor_id
               ) subj ON TRUE
               LEFT JOIN LATERAL (
                   SELECT json_agg(json_build_object(
                       'availability_id', availability_id,
                       'day_of_week', day_of_week,
                       'start_time', start_time,
                       'end_time', end_time
                   ) ORDER BY day_of_week, start_time) AS slots
                   FROM tutor_availability
                   WHERE tutor_id = t.tutor_id
               ) avail ON TRUE
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

    def get_avg_rating(self, tutor_id: int) -> dict:
        # v_tutor_ratings only contains tutors with ≥1 review (INNER JOIN +
        # GROUP BY). For a tutor with no reviews we still hand the caller
        # back the same "empty stats" shape the inlined query used to emit
        # so response serialisation stays stable.
        row = self.fetch_one(
            """SELECT avg_r1, avg_r2, avg_r3, avg_r4, review_count
               FROM v_tutor_ratings WHERE tutor_id = %s""",
            (tutor_id,),
        )
        if row is None:
            return {"avg_r1": None, "avg_r2": None, "avg_r3": None, "avg_r4": None, "review_count": 0}
        return row

    def get_active_student_count(self, tutor_id: int) -> int:
        row = self.fetch_one(
            "SELECT active_count AS cnt FROM v_tutor_active_students WHERE tutor_id = %s",
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
        validate_columns(list(flags.keys()), self.VISIBILITY_COLUMNS)
        if not flags:
            return
        set_parts = [psql.SQL("{} = %s").format(psql.Identifier(col)) for col in flags]
        query = psql.SQL("UPDATE tutors SET {} WHERE tutor_id = %s").format(
            psql.SQL(", ").join(set_parts)
        )
        params = list(flags.values()) + [tutor_id]
        self.execute(query.as_string(self.conn), tuple(params))

    def update_profile(self, tutor_id: int, **fields) -> None:
        validate_columns(list(fields.keys()), self.PROFILE_COLUMNS)
        if not fields:
            return
        set_parts = [psql.SQL("{} = %s").format(psql.Identifier(col)) for col in fields]
        query = psql.SQL("UPDATE tutors SET {} WHERE tutor_id = %s").format(
            psql.SQL(", ").join(set_parts)
        )
        params = list(fields.values()) + [tutor_id]
        self.execute(query.as_string(self.conn), tuple(params))
