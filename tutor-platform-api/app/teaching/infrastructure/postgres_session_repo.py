from app.shared.infrastructure.base_repository import BaseRepository
from app.shared.infrastructure.column_validation import validate_columns
from app.teaching.domain.ports import ISessionRepository


class PostgresSessionRepository(BaseRepository, ISessionRepository):

    _ALLOWED_UPDATE_COLUMNS = {"session_date", "hours", "content_summary", "homework",
                               "student_performance", "next_plan", "visible_to_parent"}

    def validate_update_fields(self, fields: list[str]) -> None:
        """Public guard: accept only columns this repo is willing to UPDATE."""
        validate_columns(fields, self._ALLOWED_UPDATE_COLUMNS)

    def get_match_for_create(self, match_id: int) -> dict | None:
        return self.fetch_one(
            """SELECT m.match_id, m.status, t.user_id AS tutor_user_id
               FROM matches m INNER JOIN tutors t ON m.tutor_id = t.tutor_id
               WHERE m.match_id = %s""",
            (match_id,),
        )

    def get_match_participants(self, match_id: int) -> dict | None:
        return self.fetch_one(
            """SELECT m.match_id, t.user_id AS tutor_user_id, st.parent_user_id
               FROM matches m
               INNER JOIN tutors t ON m.tutor_id = t.tutor_id
               INNER JOIN students st ON m.student_id = st.student_id
               WHERE m.match_id = %s""",
            (match_id,),
        )

    def create(self, match_id, session_date, hours, content_summary, homework,
               student_performance, next_plan, visible_to_parent) -> int:
        return self.execute_returning_id(
            """INSERT INTO sessions
                (match_id, session_date, hours, content_summary, homework,
                 student_performance, next_plan, visible_to_parent, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
               RETURNING session_id""",
            (match_id, session_date, hours, content_summary, homework,
             student_performance, next_plan, visible_to_parent),
        )

    def list_by_match(self, match_id: int, parent_only: bool = False) -> list[dict]:
        if parent_only:
            return self.fetch_all(
                "SELECT * FROM sessions WHERE match_id = %s AND visible_to_parent = TRUE ORDER BY session_date DESC",
                (match_id,),
            )
        return self.fetch_all(
            "SELECT * FROM sessions WHERE match_id = %s ORDER BY session_date DESC",
            (match_id,),
        )

    def get_by_id(self, session_id: int) -> dict | None:
        return self.fetch_one("SELECT * FROM sessions WHERE session_id = %s", (session_id,))

    def update(self, session_id: int, fields: dict) -> None:
        self.safe_update("sessions", "session_id", session_id, fields,
                         self._ALLOWED_UPDATE_COLUMNS, extra_set="updated_at = NOW()")

    def insert_edit_log(self, session_id, field_name, old_value, new_value) -> None:
        self.execute(
            """INSERT INTO session_edit_logs (session_id, field_name, old_value, new_value, edited_at)
               VALUES (%s, %s, %s, %s, NOW())""",
            (session_id, field_name,
             str(old_value) if old_value is not None else None,
             str(new_value) if new_value is not None else None),
        )

    def get_edit_logs(self, session_id: int) -> list[dict]:
        return self.fetch_all(
            "SELECT * FROM session_edit_logs WHERE session_id = %s ORDER BY edited_at DESC",
            (session_id,),
        )
