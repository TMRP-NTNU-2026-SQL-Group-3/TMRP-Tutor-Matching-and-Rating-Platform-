from app.identity.domain.ports import IUserRepository
from app.shared.infrastructure.base_repository import BaseRepository


class PostgresUserRepository(BaseRepository, IUserRepository):

    def find_by_username(self, username: str) -> dict | None:
        return self.fetch_one("SELECT * FROM users WHERE username = %s", (username,))

    def find_by_id(self, user_id: int) -> dict | None:
        return self.fetch_one("SELECT * FROM users WHERE user_id = %s", (user_id,))

    def register_user(
        self, username: str, password_hash: str, display_name: str,
        role: str, phone: str | None = None, email: str | None = None,
    ) -> int:
        self.cursor.execute(
            "INSERT INTO users (username, password_hash, display_name, role, phone, email) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING user_id",
            (username, password_hash, display_name, role, phone, email),
        )
        user_id = self.cursor.fetchone()[0]
        if role == "tutor":
            self.cursor.execute("INSERT INTO tutors (user_id) VALUES (%s)", (user_id,))
        return user_id
