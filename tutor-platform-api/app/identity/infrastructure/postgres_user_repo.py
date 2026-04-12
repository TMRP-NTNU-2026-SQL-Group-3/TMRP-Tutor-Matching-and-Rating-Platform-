from psycopg2 import errors as pg_errors

from app.identity.domain.exceptions import DuplicateUsernameError
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
        # The service pre-checks find_by_username, but two concurrent
        # registrations can still race past the check; translate the unique
        # constraint violation into the domain error here so callers see a
        # single exception type regardless of which path tripped.
        try:
            self.cursor.execute(
                "INSERT INTO users (username, password_hash, display_name, role, phone, email) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING user_id",
                (username, password_hash, display_name, role, phone, email),
            )
        except pg_errors.UniqueViolation as e:
            raise DuplicateUsernameError() from e
        user_id = self.cursor.fetchone()[0]
        if role == "tutor":
            self.cursor.execute("INSERT INTO tutors (user_id) VALUES (%s)", (user_id,))
        return user_id
