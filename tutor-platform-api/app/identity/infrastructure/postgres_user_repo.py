from psycopg2 import errors as pg_errors
from psycopg2 import sql as psql

from app.identity.domain.exceptions import DuplicateUsernameError
from app.identity.domain.ports import IUserRepository
from app.shared.infrastructure.base_repository import BaseRepository
from app.shared.infrastructure.database_tx import transaction
from app.shared.infrastructure.password_history import save_password_history as _persist_history

_UPDATABLE_COLUMNS = frozenset({'display_name', 'phone', 'email'})


class PostgresUserRepository(BaseRepository, IUserRepository):

    def find_by_username(self, username: str) -> dict | None:
        return self.fetch_one("SELECT * FROM users WHERE username = %s", (username,))

    def find_by_id(self, user_id: int) -> dict | None:
        return self.fetch_one("SELECT * FROM users WHERE user_id = %s", (user_id,))

    def register_user(
        self, username: str, password_hash: str, display_name: str,
        role: str, phone: str | None = None, email: str | None = None,
    ) -> int:
        # Both INSERTs must be atomic: a crash after the users row is written
        # but before tutors is written would leave an orphaned account.
        # transaction() is idempotent — nested calls yield through without an
        # extra commit, so the outer router transaction still owns the lifecycle.
        with transaction(self.conn):
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

    def update_me(self, user_id: int, *, fields: dict) -> None:
        safe = {k: v for k, v in fields.items() if k in _UPDATABLE_COLUMNS}
        if not safe:
            return
        set_parts = [psql.SQL("{} = %s").format(psql.Identifier(k)) for k in safe]
        query = psql.SQL("UPDATE users SET {} WHERE user_id = %s").format(
            psql.SQL(", ").join(set_parts))
        self.cursor.execute(query, list(safe.values()) + [user_id])

    def update_password(self, user_id: int, *, password_hash: str) -> None:
        self.cursor.execute(
            "UPDATE users SET password_hash = %s WHERE user_id = %s",
            (password_hash, user_id),
        )

    def save_password_history(self, user_id: int, password_hash: str) -> None:
        _persist_history(self.cursor, user_id, password_hash)

    def get_recent_password_hashes(self, user_id: int, limit: int = 5) -> list[str]:
        rows = self.fetch_all(
            "SELECT password_hash FROM password_history "
            "WHERE user_id = %s ORDER BY changed_at DESC LIMIT %s",
            (user_id, limit),
        )
        return [r["password_hash"] for r in rows]
