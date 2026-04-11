from .base import BaseRepository


class AuthRepository(BaseRepository):
    """帳號相關之資料存取操作。"""

    def find_by_username(self, username: str) -> dict | None:
        sql = "SELECT * FROM users WHERE username = %s"
        return self.fetch_one(sql, (username,))

    def find_by_id(self, user_id: int) -> dict | None:
        sql = "SELECT * FROM users WHERE user_id = %s"
        return self.fetch_one(sql, (user_id,))

    def create_user(
        self,
        username: str,
        password_hash: str,
        display_name: str,
        role: str,
        phone: str | None = None,
        email: str | None = None,
    ) -> int:
        sql = """
            INSERT INTO users (username, password_hash, display_name, role, phone, email)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING user_id
        """
        return self.execute_returning_id(
            sql, (username, password_hash, display_name, role, phone, email)
        )

    def register_user(
        self,
        username: str,
        password_hash: str,
        display_name: str,
        role: str,
        phone: str | None = None,
        email: str | None = None,
    ) -> int:
        """原子性註冊：建立 User，若為老師則一併建立 Tutors 記錄。
        呼叫端須在 transaction() 上下文中使用，由交易管理器負責 commit/rollback。
        """
        self.cursor.execute(
            "INSERT INTO users (username, password_hash, display_name, role, phone, email) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING user_id",
            (username, password_hash, display_name, role, phone, email),
        )
        user_id = self.cursor.fetchone()[0]
        if role == "tutor":
            self.cursor.execute("INSERT INTO tutors (user_id) VALUES (%s)", (user_id,))
        return user_id
