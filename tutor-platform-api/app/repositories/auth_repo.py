from .base import BaseRepository


class AuthRepository(BaseRepository):
    """帳號相關之資料存取操作。"""

    def find_by_username(self, username: str) -> dict | None:
        sql = "SELECT * FROM Users WHERE username = ?"
        return self.fetch_one(sql, (username,))

    def find_by_id(self, user_id: int) -> dict | None:
        sql = "SELECT * FROM Users WHERE user_id = ?"
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
            INSERT INTO Users (username, password_hash, display_name, role, phone, email)
            VALUES (?, ?, ?, ?, ?, ?)
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
        """原子性註冊：建立 User，若為老師則一併建立 Tutors 記錄，最後才 commit。"""
        self.cursor.execute(
            "INSERT INTO Users (username, password_hash, display_name, role, phone, email) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (username, password_hash, display_name, role, phone, email),
        )
        self.cursor.execute("SELECT @@IDENTITY")
        user_id = self.cursor.fetchone()[0]
        if role == "tutor":
            self.cursor.execute("INSERT INTO Tutors (user_id) VALUES (?)", (user_id,))
        self.conn.commit()
        return user_id
