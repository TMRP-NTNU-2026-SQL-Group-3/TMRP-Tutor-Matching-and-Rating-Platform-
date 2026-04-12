import logging
import re

logger = logging.getLogger("app")

_SAFE_COLUMN_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,62}$')


def validate_column_name(col: str) -> bool:
    """檢查單一欄位名稱是否僅含合法識別字元。

    Bug #8：白名單正則限制長度 ≤ 63（PostgreSQL identifier 上限），
    並在 quote_columns 等下游函式以雙引號包覆，雙重防護動態 SQL 拼接的
    SQL 注入風險。維護者請勿繞過 validate_columns() 而以原始字串拼 SQL。
    """
    if not isinstance(col, str):
        return False
    return bool(_SAFE_COLUMN_NAME.match(col))


def validate_columns(columns: list[str]) -> None:
    """驗證一批欄位名稱，不合法時拋出 ValueError。"""
    for col in columns:
        if not validate_column_name(col):
            raise ValueError(f"不合法的欄位名稱：{col!r}")


def quote_columns(columns: list[str]) -> str:
    """將欄位名稱以雙引號引用組合（PostgreSQL 識別符引用方式）。"""
    return ", ".join(f'"{col}"' for col in columns)


def coerce_csv_value(val):
    """將 CSV 字串值轉換為適合 PostgreSQL 的型別。"""
    if val is None:
        return None
    if not val or val.strip() == "":
        return None
    if val in ('True', 'true'):
        return True
    if val in ('False', 'false'):
        return False
    return val


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
        return getattr(self.conn, '_in_tx', False)

    def execute(self, sql: str, params: tuple = ()) -> None:
        """執行寫入操作（INSERT / UPDATE / DELETE）。
        若在交易中則不自動 commit，由交易管理器負責。
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
