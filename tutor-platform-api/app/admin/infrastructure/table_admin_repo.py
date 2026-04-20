from psycopg2 import sql

from app.admin.infrastructure.csv_utils import coerce_csv_value, validate_columns
from app.shared.infrastructure.base_repository import BaseRepository


class TableAdminRepository(BaseRepository):
    """Infrastructure helper for admin-level table operations: bulk counts,
    deletes, CSV-shaped inserts, and serial-sequence resets. All table names
    must be pre-validated against the ALLOWED_TABLES whitelist by the caller."""

    def get_schema_columns(self, table: str) -> set[str]:
        """Return the set of column names defined on `table` in the current
        database. Used by B9 to reject CSV headers that reference columns the
        target table does not have, before the INSERT would surface a raw
        psycopg2 error that leaks schema detail to the admin UI."""
        rows = self.fetch_all(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = %s",
            (table,),
        )
        return {r["column_name"] for r in rows}

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
        # Rebases every SERIAL/IDENTITY sequence to MAX(col) of the current
        # table contents so the next auto-generated id cannot collide with an
        # imported row that hard-coded an id. The reset is strictly MAX-based
        # — `setval(..., MAX, true)` makes the next `nextval` return MAX+1
        # (equivalently, `MAX+1, false`); we never lower a sequence below its
        # current MAX and never raise it past the last stored row.
        # table_schema is constrained to the active schema so a same-named
        # table in another schema cannot leak into the match.
        for table in table_names:
            self.cursor.execute(
                "SELECT column_name, pg_get_serial_sequence(%s, column_name) AS seq "
                "FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "  AND table_name = %s "
                "  AND column_default LIKE 'nextval%%'",
                (table, table),
            )
            for row in self.cursor.fetchall():
                col_name, seq_name = row[0], row[1]
                if seq_name:
                    # setval(seq, MAX+1, false) makes the next nextval() return
                    # exactly MAX+1. For an empty table COALESCE yields 0 → the
                    # next nextval returns 1, matching PostgreSQL's default
                    # starting value. Never lowered below MAX(col), so a hand-
                    # coded id in the imported data cannot collide with a
                    # subsequent auto-assigned id.
                    stmt = sql.SQL(
                        "SELECT setval({seq}, "
                        "COALESCE((SELECT MAX({col}) FROM {tbl}), 0) + 1, false)"
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

    def get_user_role(self, user_id: int) -> str | None:
        row = self.fetch_one(
            "SELECT role FROM users WHERE user_id = %s", (user_id,)
        )
        return row["role"] if row else None

    def anonymize_user(self, user_id: int) -> bool:
        """GDPR 'right to erasure' friendly counterpart to DELETE.

        Replaces PII columns with deterministic placeholders and invalidates
        the credential, but keeps the row so that audit-only FKs (matches.
        terminated_by, reviews.reviewer_user_id, etc.) stay resolvable. The
        password_hash is set to a non-verifying sentinel so no password will
        ever match on login again.

        Returns True when a row was updated, False when user_id is unknown.
        """
        placeholder_username = f"deleted_user_{user_id}"
        self.cursor.execute(
            """
            UPDATE users SET
                username = %s,
                password_hash = 'ANONYMIZED',
                display_name = 'Deleted User',
                phone = NULL,
                email = NULL
            WHERE user_id = %s
            """,
            (placeholder_username, user_id),
        )
        return self.cursor.rowcount > 0

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
