from app.repositories.base import BaseRepository
from app.utils.access_bits import to_access_bit


class SessionRepository(BaseRepository):

    def get_match_for_create(self, match_id: int) -> dict | None:
        """取得配對資訊（含老師 user_id 與狀態），用於新增日誌時的驗證。"""
        return self.fetch_one(
            """
            SELECT m.match_id, m.status, t.user_id AS tutor_user_id
            FROM Matches m
            INNER JOIN Tutors t ON m.tutor_id = t.tutor_id
            WHERE m.match_id = ?
            """,
            (match_id,),
        )

    def get_match_participants(self, match_id: int) -> dict | None:
        """取得配對的老師及家長 user_id，用於授權查詢。"""
        return self.fetch_one(
            """
            SELECT m.match_id, t.user_id AS tutor_user_id, st.parent_user_id
            FROM (Matches m
            INNER JOIN Tutors t ON m.tutor_id = t.tutor_id)
            INNER JOIN Students st ON m.student_id = st.student_id
            WHERE m.match_id = ?
            """,
            (match_id,),
        )

    def create(
        self, match_id: int, session_date, hours: float,
        content_summary: str | None, homework: str | None,
        student_performance: str | None, next_plan: str | None,
        visible_to_parent: bool,
    ) -> int:
        return self.execute_returning_id(
            """
            INSERT INTO Sessions
                (match_id, session_date, hours, content_summary, homework,
                 student_performance, next_plan, visible_to_parent, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, Now(), Now())
            """,
            (
                match_id, session_date, hours,
                content_summary, homework,
                student_performance, next_plan,
                to_access_bit(visible_to_parent),
            ),
        )

    def list_by_match(self, match_id: int, parent_only: bool = False) -> list[dict]:
        if parent_only:
            return self.fetch_all(
                "SELECT * FROM Sessions WHERE match_id = ? AND visible_to_parent = -1 ORDER BY session_date DESC",
                (match_id,),
            )
        return self.fetch_all(
            "SELECT * FROM Sessions WHERE match_id = ? ORDER BY session_date DESC",
            (match_id,),
        )

    def get_by_id(self, session_id: int) -> dict | None:
        return self.fetch_one(
            "SELECT * FROM Sessions WHERE session_id = ?",
            (session_id,),
        )

    def update(self, session_id: int, fields: dict) -> None:
        """更新指定欄位，fields 為 {column: value} dict。"""
        set_clauses = ", ".join(f"{k} = ?" for k in fields)
        values = tuple(fields.values()) + (session_id,)
        self.execute(
            f"UPDATE Sessions SET {set_clauses}, updated_at = Now() WHERE session_id = ?",
            values,
        )

    def insert_edit_log(self, session_id: int, field_name: str, old_value: str | None, new_value: str | None) -> None:
        self.execute(
            """
            INSERT INTO Session_Edit_Logs (session_id, field_name, old_value, new_value, edited_at)
            VALUES (?, ?, ?, ?, Now())
            """,
            (session_id, field_name, str(old_value) if old_value is not None else None,
             str(new_value) if new_value is not None else None),
        )

    def get_edit_logs(self, session_id: int) -> list[dict]:
        return self.fetch_all(
            "SELECT * FROM Session_Edit_Logs WHERE session_id = ? ORDER BY edited_at DESC",
            (session_id,),
        )
