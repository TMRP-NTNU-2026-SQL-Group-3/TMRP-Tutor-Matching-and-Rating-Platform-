import psycopg2
from psycopg2 import pool

from app.shared.infrastructure.config import settings

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


def _require_pool() -> pool.ThreadedConnectionPool:
    """取得連線池物件；若尚未初始化則拋出明確錯誤。"""
    if _pool is None:
        raise RuntimeError(
            "Database pool not initialized. 請先呼叫 init_pool()，"
            "或確認應用是透過 lifespan 啟動（非單獨匯入模組）。"
        )
    return _pool


def get_db():
    """FastAPI 依賴注入：從連線池取得連線，請求結束歸還。

    歸還前一律 rollback，確保連線不會帶著未提交或已中止的交易回到連線池，
    避免下一位使用者收到 InFailedSqlTransaction 錯誤。
    已 commit 的交易 rollback 為 no-op，不影響正確性。
    """
    pool_ref = _require_pool()
    conn = pool_ref.getconn()
    try:
        yield conn
    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        pool_ref.putconn(conn)


def get_connection():
    """背景任務用：從連線池取得連線。呼叫者需自行呼叫 release_connection() 歸還。"""
    return _require_pool().getconn()


def release_connection(conn):
    """歸還連線至連線池。歸還前一律 rollback，與 get_db() 行為一致。"""
    try:
        conn.rollback()
    except Exception:
        pass
    _require_pool().putconn(conn)


if __name__ == "__main__":
    import sys

    if "--init" in sys.argv:
        from app.init_db import initialize_database
        from app.shared.infrastructure.logger import setup_logger

        setup_logger()
        try:
            initialize_database()
            print("[成功] 資料庫初始化完成")
        except Exception as e:
            print(f"[錯誤] 資料庫初始化失敗: {e}")
            sys.exit(1)
    else:
        print("Usage: python -m app.shared.infrastructure.database --init")
        sys.exit(1)
