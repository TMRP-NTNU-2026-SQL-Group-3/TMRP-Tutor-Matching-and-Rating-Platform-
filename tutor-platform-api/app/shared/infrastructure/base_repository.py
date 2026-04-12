"""Minimal DB-access helper shared by infrastructure repositories.

Responsibilities are deliberately narrow: open/close a cursor, run SQL,
fetch rows as dicts, paginate, and offer a whitelist-enforced UPDATE.
Column validation lives in `column_validation` — do not re-add it here.
"""

import logging

from app.shared.infrastructure.column_validation import validate_columns

logger = logging.getLogger("app")


class BaseRepository:
    def __init__(self, conn):
        self.conn = conn
        self.cursor = conn.cursor()

    def close(self):
        try:
            self.cursor.close()
        except Exception:
            logger.exception("Failed to close cursor")

    def safe_update(self, table: str, id_col: str, id_val, updates: dict,
                    allowed_columns: set, extra_set: str = "") -> None:
        """Parameterised UPDATE with mandatory column whitelist."""
        validate_columns(list(updates.keys()), allowed_columns)
        set_clause = ", ".join(f"{col} = %s" for col in updates)
        if extra_set:
            set_clause += ", " + extra_set
        values = list(updates.values()) + [id_val]
        self.execute(
            f"UPDATE {table} SET {set_clause} WHERE {id_col} = %s",
            values,
        )

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        self.cursor.execute(sql, params)
        row = self.cursor.fetchone()
        if row is None:
            return None
        columns = [desc[0] for desc in self.cursor.description]
        return dict(zip(columns, row))

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        self.cursor.execute(sql, params)
        rows = self.cursor.fetchall()
        columns = [desc[0] for desc in self.cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def _in_transaction(self) -> bool:
        return getattr(self.conn, '_in_tx', False)

    def execute(self, sql: str, params: tuple = ()) -> None:
        """INSERT / UPDATE / DELETE. Commits unless inside an outer transaction."""
        self.cursor.execute(sql, params)
        if not self._in_transaction():
            self.conn.commit()

    def execute_returning_id(self, sql: str, params: tuple = ()) -> int:
        """Execute INSERT ... RETURNING <id> and return the new id."""
        self.cursor.execute(sql, params)
        new_id = self.cursor.fetchone()[0]
        if not self._in_transaction():
            self.conn.commit()
        return new_id

    def fetch_paginated(
        self, sql: str, params: tuple, page: int, page_size: int
    ) -> tuple[list[dict], int]:
        count_sql = f"SELECT COUNT(*) AS cnt FROM ({sql}) AS _sub"
        self.cursor.execute(count_sql, params)
        total = self.cursor.fetchone()[0]

        if total == 0:
            return [], 0

        offset = (page - 1) * page_size
        paged_sql = f"{sql} LIMIT {page_size} OFFSET {offset}"
        items = self.fetch_all(paged_sql, params)
        return items, total
