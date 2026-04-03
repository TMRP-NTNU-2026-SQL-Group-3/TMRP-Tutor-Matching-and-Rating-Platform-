from app.repositories.base import BaseRepository
from app.utils.access_bits import to_access_bit


class MatchRepository(BaseRepository):

    def create(
        self,
        tutor_id: int,
        student_id: int,
        subject_id: int,
        hourly_rate: float,
        sessions_per_week: int,
        want_trial: bool,
        invite_message: str | None,
    ) -> int:
        sql = """
            INSERT INTO Matches
                (tutor_id, student_id, subject_id, status,
                 hourly_rate, sessions_per_week, want_trial,
                 invite_message, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, Now(), Now())
        """
        want_trial_bit = to_access_bit(want_trial)
        return self.execute_returning_id(sql, (
            tutor_id, student_id, subject_id,
            hourly_rate, sessions_per_week, want_trial_bit, invite_message,
        ))

    def find_by_id(self, match_id: int) -> dict | None:
        sql = """
            SELECT m.*, s.subject_name,
                   st.name AS student_name, st.parent_user_id,
                   t.user_id AS tutor_user_id,
                   u.display_name AS tutor_display_name
            FROM (((Matches m
            INNER JOIN Subjects s ON m.subject_id = s.subject_id)
            INNER JOIN Students st ON m.student_id = st.student_id)
            INNER JOIN Tutors t ON m.tutor_id = t.tutor_id)
            INNER JOIN Users u ON t.user_id = u.user_id
            WHERE m.match_id = ?
        """
        return self.fetch_one(sql, (match_id,))

    def find_by_tutor_user_id(self, tutor_user_id: int) -> list[dict]:
        sql = """
            SELECT m.*, s.subject_name, st.name AS student_name
            FROM ((Matches m
            INNER JOIN Subjects s ON m.subject_id = s.subject_id)
            INNER JOIN Students st ON m.student_id = st.student_id)
            INNER JOIN Tutors t ON m.tutor_id = t.tutor_id
            WHERE t.user_id = ?
            ORDER BY m.updated_at DESC
        """
        return self.fetch_all(sql, (tutor_user_id,))

    def find_by_parent_user_id(self, parent_user_id: int) -> list[dict]:
        sql = """
            SELECT m.*, s.subject_name, st.name AS student_name,
                   u.display_name AS tutor_display_name
            FROM (((Matches m
            INNER JOIN Subjects s ON m.subject_id = s.subject_id)
            INNER JOIN Students st ON m.student_id = st.student_id)
            INNER JOIN Tutors t ON m.tutor_id = t.tutor_id)
            INNER JOIN Users u ON t.user_id = u.user_id
            WHERE st.parent_user_id = ?
            ORDER BY m.updated_at DESC
        """
        return self.fetch_all(sql, (parent_user_id,))

    def update_status(self, match_id: int, new_status: str) -> None:
        sql = "UPDATE Matches SET status = ?, updated_at = Now() WHERE match_id = ?"
        self.execute(sql, (new_status, match_id))

    def set_terminating(self, match_id: int, user_id: int, reason: str, previous_status: str) -> None:
        # 將 previous_status 存入 termination_reason 前綴，便於 disagree_terminate 回復
        combined_reason = f"{previous_status}|{reason}" if reason else previous_status
        sql = """
            UPDATE Matches SET status = 'terminating', terminated_by = ?,
                   termination_reason = ?, updated_at = Now()
            WHERE match_id = ?
        """
        self.execute(sql, (user_id, combined_reason, match_id))

    def clear_termination(self, match_id: int, revert_status: str) -> None:
        sql = """
            UPDATE Matches SET status = ?, terminated_by = NULL,
                   termination_reason = NULL, updated_at = Now()
            WHERE match_id = ?
        """
        self.execute(sql, (revert_status, match_id))

    def check_duplicate_active(self, tutor_id: int, student_id: int, subject_id: int) -> bool:
        sql = """
            SELECT COUNT(*) AS cnt FROM Matches
            WHERE tutor_id = ? AND student_id = ? AND subject_id = ?
            AND status NOT IN ('cancelled', 'rejected', 'ended')
        """
        row = self.fetch_one(sql, (tutor_id, student_id, subject_id))
        return row["cnt"] > 0 if row else False
