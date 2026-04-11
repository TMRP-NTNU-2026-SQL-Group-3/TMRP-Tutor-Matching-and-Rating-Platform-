from app.repositories.base import BaseRepository


class ReviewRepository(BaseRepository):

    def get_match_for_create(self, match_id: int) -> dict | None:
        """取得配對資訊（含老師及家長 user_id），用於新增評價時的驗證。"""
        return self.fetch_one(
            """
            SELECT m.match_id, m.status, t.user_id AS tutor_user_id, st.parent_user_id
            FROM matches m
            INNER JOIN tutors t ON m.tutor_id = t.tutor_id
            INNER JOIN students st ON m.student_id = st.student_id
            WHERE m.match_id = %s
            """,
            (match_id,),
        )

    def get_match_participants(self, match_id: int) -> dict | None:
        """取得配對的參與者 user_id，用於查詢授權。"""
        return self.fetch_one(
            """
            SELECT m.match_id, t.user_id AS tutor_user_id, st.parent_user_id
            FROM matches m
            INNER JOIN tutors t ON m.tutor_id = t.tutor_id
            INNER JOIN students st ON m.student_id = st.student_id
            WHERE m.match_id = %s
            """,
            (match_id,),
        )

    def find_existing(self, match_id: int, reviewer_user_id: int, review_type: str) -> dict | None:
        return self.fetch_one(
            """
            SELECT review_id FROM reviews
            WHERE match_id = %s AND reviewer_user_id = %s AND review_type = %s
            """,
            (match_id, reviewer_user_id, review_type),
        )

    def create(
        self, match_id: int, reviewer_user_id: int, review_type: str,
        rating_1: int, rating_2: int, rating_3: int | None, rating_4: int | None,
        personality_comment: str | None, comment: str | None,
    ) -> int:
        return self.execute_returning_id(
            """
            INSERT INTO reviews
                (match_id, reviewer_user_id, review_type,
                 rating_1, rating_2, rating_3, rating_4,
                 personality_comment, comment, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            RETURNING review_id
            """,
            (
                match_id, reviewer_user_id, review_type,
                rating_1, rating_2, rating_3, rating_4,
                personality_comment, comment,
            ),
        )

    def list_by_match(self, match_id: int) -> list[dict]:
        return self.fetch_all(
            """
            SELECT r.*, u.display_name AS reviewer_name
            FROM reviews r
            INNER JOIN users u ON r.reviewer_user_id = u.user_id
            WHERE r.match_id = %s
            ORDER BY r.created_at DESC
            """,
            (match_id,),
        )

    def list_by_tutor(self, tutor_id: int) -> list[dict]:
        return self.fetch_all(
            """
            SELECT r.*, u.display_name AS reviewer_name
            FROM reviews r
            INNER JOIN users u ON r.reviewer_user_id = u.user_id
            INNER JOIN matches m ON r.match_id = m.match_id
            WHERE m.tutor_id = %s AND r.review_type = 'parent_to_tutor'
            ORDER BY r.created_at DESC
            """,
            (tutor_id,),
        )

    def get_for_update(self, review_id: int) -> dict | None:
        return self.fetch_one(
            "SELECT reviewer_user_id, is_locked FROM reviews WHERE review_id = %s",
            (review_id,),
        )

    ALLOWED_COLUMNS = {"rating_1", "rating_2", "rating_3", "rating_4",
                       "personality_comment", "comment"}

    def update(self, review_id: int, updates: dict) -> None:
        """更新評價的可修改欄位（updates 的 key 必須是合法欄位名稱）。"""
        self.safe_update("reviews", "review_id", review_id, updates,
                         self.ALLOWED_COLUMNS, extra_set="updated_at = NOW()")
