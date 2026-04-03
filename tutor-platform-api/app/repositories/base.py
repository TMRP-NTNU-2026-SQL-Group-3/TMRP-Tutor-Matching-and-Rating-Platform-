class BaseRepository:
    """所有 Repository 之基礎類別，提供通用之資料存取方法。"""

    def __init__(self, conn):
        self.conn = conn
        self.cursor = conn.cursor()

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

    def execute(self, sql: str, params: tuple = ()) -> None:
        """執行寫入操作（INSERT / UPDATE / DELETE）並提交交易。"""
        self.cursor.execute(sql, params)
        self.conn.commit()

    def execute_returning_id(self, sql: str, params: tuple = ()) -> int:
        """執行 INSERT 並回傳自動產生之主鍵值（AutoNumber）。"""
        self.cursor.execute(sql, params)
        self.cursor.execute("SELECT @@IDENTITY")
        new_id = self.cursor.fetchone()[0]
        self.conn.commit()
        return new_id

    def fetch_paginated(
        self, sql: str, params: tuple, page: int, page_size: int
    ) -> tuple[list[dict], int]:
        """
        執行分頁查詢。
        由於 MS Access 不支援 LIMIT/OFFSET 語法，故先取回全部結果，
        再於 Python 端進行分頁切割。
        回傳值：(items, total_count)
        """
        all_rows = self.fetch_all(sql, params)
        total = len(all_rows)
        start = (page - 1) * page_size
        items = all_rows[start : start + page_size]
        return items, total
