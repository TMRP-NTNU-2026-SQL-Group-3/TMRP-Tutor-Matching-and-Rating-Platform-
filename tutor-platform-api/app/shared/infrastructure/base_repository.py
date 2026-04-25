"""Minimal DB-access helper shared by infrastructure repositories.

Responsibilities are deliberately narrow: open/close a cursor, run SQL,
fetch rows as dicts, paginate, and offer a whitelist-enforced UPDATE.
Column validation lives in `column_validation` — do not re-add it here.
"""

import logging

from psycopg2 import sql as psql

from app.shared.infrastructure.column_validation import validate_columns
from app.shared.infrastructure.database_tx import _is_in_tx

logger = logging.getLogger("app")


def escape_like(value: str) -> str:
    """Escape LIKE wildcard characters so *value* is matched literally.

    Must be paired with ``ESCAPE '\\'`` in the SQL clause.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class BaseRepository:
    def __init__(self, conn):
        self.conn = conn
        self.cursor = conn.cursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # Guarantees the cursor is released when the repo is used as a
        # `with` block. Returning False lets the original exception (if any)
        # propagate after cleanup.
        self.close()
        return False

    def close(self):
        # DB-L02: Intentionally broad catch — cursor cleanup must not mask
        # the original exception that caused the caller to close the repo.
        # Log + swallow so the connection can still be returned to the pool.
        try:
            if self.cursor and not self.cursor.closed:
                self.cursor.close()
        except Exception:
            logger.exception("Failed to close cursor")

    def safe_update(self, table: str, id_col: str, id_val, updates: dict,
                    allowed_columns: set, update_timestamp: bool = False) -> None:
        """Parameterised UPDATE with mandatory column whitelist."""
        validate_columns(list(updates.keys()), allowed_columns)
        set_parts = [psql.SQL("{} = %s").format(psql.Identifier(col)) for col in updates]
        if update_timestamp:
            set_parts.append(psql.SQL("updated_at = NOW()"))
        query = psql.SQL("UPDATE {} SET {} WHERE {} = %s").format(
            psql.Identifier(table),
            psql.SQL(", ").join(set_parts),
            psql.Identifier(id_col),
        )
        values = list(updates.values()) + [id_val]
        self.execute(query, values)

    def fetch_one(self, sql: "str | psql.Composable", params: tuple = ()) -> dict | None:
        self.cursor.execute(sql, params)
        row = self.cursor.fetchone()
        if row is None:
            return None
        columns = [desc[0] for desc in self.cursor.description]
        return dict(zip(columns, row))

    def fetch_all(self, sql: "str | psql.Composable", params: tuple = ()) -> list[dict]:
        self.cursor.execute(sql, params)
        rows = self.cursor.fetchall()
        columns = [desc[0] for desc in self.cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def _in_transaction(self) -> bool:
        return _is_in_tx(self.conn)

    def execute(self, sql: "str | psql.Composable", params: tuple = ()) -> None:
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
        count_sql = psql.SQL("SELECT COUNT(*) AS cnt FROM ({inner}) AS _sub").format(
            inner=psql.SQL(sql)
        )
        self.cursor.execute(count_sql, params)
        total = self.cursor.fetchone()[0]

        if total == 0:
            return [], 0

        # Surface an out-of-range page as an explicit error instead of silently
        # returning an empty list. Clients cannot distinguish "past the last
        # page" from "filter matched nothing" without this check, which makes
        # pagination bugs in callers hard to diagnose. Page 1 is always valid
        # (even with total=0, we returned early above).
        max_page = (total + page_size - 1) // page_size
        if page > max_page:
            raise ValueError(
                f"page {page} out of range (1..{max_page}, total={total})"
            )

        offset = (page - 1) * page_size
        paged_sql = sql + " LIMIT %s OFFSET %s"
        items = self.fetch_all(paged_sql, tuple(params) + (page_size, offset))
        return items, total
