from app.admin.infrastructure.csv_utils import (
    coerce_csv_value,
    quote_columns,
    validate_columns,
)
from app.shared.infrastructure.base_repository import BaseRepository


class TableAdminRepository(BaseRepository):
    """Infrastructure helper for admin-level table operations: bulk counts,
    deletes, CSV-shaped inserts, and serial-sequence resets. All table names
    must be pre-validated against the ALLOWED_TABLES whitelist by the caller."""

    def count(self, table: str) -> int:
        row = self.fetch_one(f"SELECT COUNT(*) AS cnt FROM {table}")
        return (row and row["cnt"]) or 0

    def count_all(self, tables) -> dict:
        return {t: self.count(t) for t in tables}

    def delete_all(self, table: str) -> None:
        self.cursor.execute(f"DELETE FROM {table}")

    def delete_users_except(self, admin_user_id: int) -> None:
        self.cursor.execute("DELETE FROM users WHERE user_id <> %s", (admin_user_id,))

    def select_all(self, table: str) -> list[dict]:
        return self.fetch_all(f"SELECT * FROM {table}")

    def insert_csv_row(self, table: str, columns: list[str], raw_values: list) -> None:
        validate_columns(columns)
        placeholders = ", ".join(["%s"] * len(columns))
        col_names = quote_columns(columns)
        sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"
        values = tuple(coerce_csv_value(v) for v in raw_values)
        self.cursor.execute(sql, values)

    def reset_serial_sequences(self, table_names) -> None:
        for table in table_names:
            self.cursor.execute(
                "SELECT column_name, pg_get_serial_sequence(%s, column_name) AS seq "
                "FROM information_schema.columns "
                "WHERE table_name = %s AND column_default LIKE 'nextval%%'",
                (table, table),
            )
            for row in self.cursor.fetchall():
                col_name, seq_name = row[0], row[1]
                if seq_name:
                    self.cursor.execute(
                        f"SELECT setval('{seq_name}', COALESCE((SELECT MAX(\"{col_name}\") FROM {table}), 0) + 1, false)"
                    )

    def savepoint(self, name: str = "row_sp") -> None:
        self.cursor.execute(f"SAVEPOINT {name}")

    def release_savepoint(self, name: str = "row_sp") -> None:
        self.cursor.execute(f"RELEASE SAVEPOINT {name}")

    def rollback_to_savepoint(self, name: str = "row_sp") -> None:
        self.cursor.execute(f"ROLLBACK TO SAVEPOINT {name}")

    def list_users(self) -> list[dict]:
        return self.fetch_all(
            "SELECT user_id, username, role, display_name, phone, email, created_at "
            "FROM users ORDER BY user_id"
        )

    def role_counts(self) -> dict:
        rows = self.fetch_all("SELECT role, COUNT(*) AS cnt FROM users GROUP BY role")
        return {r["role"]: r["cnt"] for r in rows}

    def match_status_counts(self) -> dict:
        rows = self.fetch_all("SELECT status, COUNT(*) AS cnt FROM matches GROUP BY status")
        return {r["status"]: r["cnt"] for r in rows}
