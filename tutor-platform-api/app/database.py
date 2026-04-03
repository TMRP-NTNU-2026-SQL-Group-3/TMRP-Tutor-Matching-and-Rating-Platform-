import time

import pyodbc

from app.config import settings


def get_connection(retries: int = 3, delay: float = 0.5) -> pyodbc.Connection:
    """
    建立並回傳一個新的 MS Access ODBC 連線。
    內建重試機制以應對多 process 併發存取時的暫時性鎖定錯誤。

    參數：
        retries: 最大重試次數（預設 3 次）
        delay: 每次重試前的等待秒數（預設 0.5 秒）
    """
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        rf"DBQ={settings.access_db_path};"
    )
    for attempt in range(retries):
        try:
            return pyodbc.connect(conn_str)
        except pyodbc.Error:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise


def get_db():
    """FastAPI 依賴注入用之 generator。每次請求建立連線，請求結束時關閉。"""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    if "--init" in sys.argv:
        from app.init_db import initialize_database
        from app.utils.logger import setup_logger

        setup_logger()
        try:
            initialize_database()
            print("[成功] 資料庫初始化完成")
        except Exception as e:
            print(f"[錯誤] 資料庫初始化失敗: {e}")
            sys.exit(1)
    else:
        print("Usage: python -m app.database --init")
        sys.exit(1)
