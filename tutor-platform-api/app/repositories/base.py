import logging

from app.database_tx import _in_transaction as _tx_set
from app.utils.columns import validate_column_name

logger = logging.getLogger("app")


class BaseRepository:
    """所有 Repository 之基礎類別，提供通用之資料存取方法。"""

    def __init__(self, conn):
        self.conn = conn
        self.cursor = conn.cursor()

    def close(self):
        """關閉 cursor（connection 由外層管理）。"""
        try:
            self.cursor.close()
        except Exception:
            logger.exception("Failed to close cursor")

    @staticmethod
    def validate_columns(columns: list, allowed: set | None = None) -> None:
        """驗證欄位名稱僅含合法識別字元，並可選擇限制於白名單。"""
        for col in columns:
            if not validate_column_name(col):
                raise ValueError(f"不合法的欄位名稱：{col!r}")
            if allowed and col not in allowed:
                raise ValueError(f"不允許更新的欄位：{col!r}")

    def safe_update(self, table: str, id_col: str, id_val, updates: dict,
                    allowed_columns: set, extra_set: str = "") -> None:
        """安全的動態 UPDATE，強制驗證欄位白名單。"""
        self.validate_columns(list(updates.keys()), allowed_columns)
        set_clause = ", ".join(f"{col} = %s" for col in updates)
        if extra_set:
            set_clause += ", " + extra_set
        values = list(updates.values()) + [id_val]
        self.execute(
            f"UPDATE {table} SET {set_clause} WHERE {id_col} = %s",
            values,
        )

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        """執行查詢並回傳單筆結果（dict 格式），查無資料時回傳 None。"""
        self.cursor.execute(sql, params)
        row = self.cursor.fetchone()
        if row is None:
            return None
        columns = [desc[0] for desc in self.cursor.description]
        return dict(zip(columns, row))

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        """執行查詢並回傳全部結果（list of dict 格式）。"""
        self.cursor.execute(sql, params)
        rows = self.cursor.fetchall()
        columns = [desc[0] for desc in self.cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def _in_transaction(self) -> bool:
        """檢查當前連線是否在 transaction() 上下文中。"""
        return id(self.conn) in _tx_set

    def execute(self, sql: str, params: tuple = ()) -> None:
        """執行寫入操作（INSERT / UPDATE / DELETE）。
        T-BIZ-03: 若在交易中則不自動 commit，由交易管理器負責。
        """
        self.cursor.execute(sql, params)
        if not self._in_transaction():
            self.conn.commit()

    def execute_returning_id(self, sql: str, params: tuple = ()) -> int:
        """
        執行 INSERT 並回傳自動產生之主鍵值。

        呼叫者的 SQL 須包含 RETURNING <id_column> 子句。
        """
        self.cursor.execute(sql, params)
        new_id = self.cursor.fetchone()[0]
        if not self._in_transaction():
            self.conn.commit()
        return new_id

    def fetch_paginated(
        self, sql: str, params: tuple, page: int, page_size: int
    ) -> tuple[list[dict], int]:
        """
        執行分頁查詢（PostgreSQL LIMIT/OFFSET）。
        回傳值：(items, total_count)
        """
        # 取得總筆數
        count_sql = f"SELECT COUNT(*) AS cnt FROM ({sql}) AS _sub"
        self.cursor.execute(count_sql, params)
        total = self.cursor.fetchone()[0]

        if total == 0:
            return [], 0

        # PostgreSQL 原生分頁
        offset = (page - 1) * page_size
        paged_sql = f"{sql} LIMIT {page_size} OFFSET {offset}"
        items = self.fetch_all(paged_sql, params)
        return items, total
