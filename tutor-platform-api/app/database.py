import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from app.config import settings

# 應用啟動時建立連線池
_pool: pool.ThreadedConnectionPool | None = None


def init_pool():
    """初始化 PostgreSQL 連線池。應在應用啟動時呼叫一次。"""
    global _pool
    _pool = pool.ThreadedConnectionPool(
        minconn=settings.db_pool_min,
        maxconn=settings.db_pool_max,
        dsn=settings.database_url,
    )


def close_pool():
    """關閉連線池。應在應用關閉時呼叫。"""
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None


def get_db():
    """FastAPI 依賴注入：從連線池取得連線，請求結束歸還。"""
    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)


def get_connection():
    """背景任務用：從連線池取得連線。呼叫者需自行呼叫 release_connection() 歸還。"""
    return _pool.getconn()


def release_connection(conn):
    """歸還連線至連線池。"""
    _pool.putconn(conn)


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
