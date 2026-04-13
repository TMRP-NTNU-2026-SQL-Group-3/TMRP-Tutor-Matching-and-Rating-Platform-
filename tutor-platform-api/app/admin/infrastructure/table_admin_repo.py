from psycopg2 import sql

from app.admin.infrastructure.csv_utils import coerce_csv_value, validate_columns
from app.shared.infrastructure.base_repository import BaseRepository


class TableAdminRepository(BaseRepository):
    """Infrastructure helper for admin-level table operations: bulk counts,
    deletes, CSV-shaped inserts, and serial-sequence resets. All table names
    must be pre-validated against the ALLOWED_TABLES whitelist by the caller."""

    def count(self, table: str) -> int:
        stmt = sql.SQL("SELECT COUNT(*) AS cnt FROM {tbl}").format(
            tbl=sql.Identifier(table)
        )
        row = self.fetch_one(stmt)
        return (row and row["cnt"]) or 0

    def count_all(self, tables) -> dict:
        return {t: self.count(t) for t in tables}

    def delete_all(self, table: str) -> None:
        stmt = sql.SQL("DELETE FROM {tbl}").format(tbl=sql.Identifier(table))
        self.cursor.execute(stmt)

    def delete_users_except(self, admin_user_id: int) -> None:
        self.cursor.execute("DELETE FROM users WHERE user_id <> %s", (admin_user_id,))

    def select_all(self, table: str) -> list[dict]:
        stmt = sql.SQL("SELECT * FROM {tbl}").format(tbl=sql.Identifier(table))
        return self.fetch_all(stmt)

    def insert_csv_row(self, table: str, columns: list[str], raw_values: list) -> None:
        validate_columns(columns)
        col_list = sql.SQL(", ").join(sql.Identifier(c) for c in columns)
        placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in columns)
        stmt = sql.SQL("INSERT INTO {tbl} ({cols}) VALUES ({vals})").format(
            tbl=sql.Identifier(table), cols=col_list, vals=placeholders,
        )
        values = tuple(coerce_csv_value(v) for v in raw_values)
        self.cursor.execute(stmt, values)

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
                    stmt = sql.SQL(
                        "SELECT setval({seq}, COALESCE((SELECT MAX({col}) FROM {tbl}), 0) + 1, false)"
                    ).format(
                        seq=sql.Literal(seq_name),
                        col=sql.Identifier(col_name),
                        tbl=sql.Identifier(table),
                    )
                    self.cursor.execute(stmt)

    def savepoint(self, name: str = "row_sp") -> None:
        stmt = sql.SQL("SAVEPOINT {sp}").format(sp=sql.Identifier(name))
        self.cursor.execute(stmt)

    def release_savepoint(self, name: str = "row_sp") -> None:
        stmt = sql.SQL("RELEASE SAVEPOINT {sp}").format(sp=sql.Identifier(name))
        self.cursor.execute(stmt)

    def rollback_to_savepoint(self, name: str = "row_sp") -> None:
        stmt = sql.SQL("ROLLBACK TO SAVEPOINT {sp}").format(sp=sql.Identifier(name))
        self.cursor.execute(stmt)

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
