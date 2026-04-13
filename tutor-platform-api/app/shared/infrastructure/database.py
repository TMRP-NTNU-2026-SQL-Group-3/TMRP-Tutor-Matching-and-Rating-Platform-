import logging

import psycopg2
from psycopg2 import pool

from app.shared.infrastructure.config import settings

logger = logging.getLogger("app.db")

_pool: pool.ThreadedConnectionPool | None = None


def init_pool():
    """Initialize the PostgreSQL connection pool. Call once at app startup."""
    global _pool
    _pool = pool.ThreadedConnectionPool(
        minconn=settings.db_pool_min,
        maxconn=settings.db_pool_max,
        dsn=settings.database_url,
    )


def close_pool():
    """Close the connection pool. Call at app shutdown."""
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None


def _require_pool() -> pool.ThreadedConnectionPool:
    """Return the pool, or raise if init_pool() was never called."""
    if _pool is None:
        raise RuntimeError(
            "Database pool not initialized. Call init_pool() first, or make "
            "sure the app is launched through its lifespan (not by importing "
            "modules in isolation)."
        )
    return _pool


def get_db():
    """FastAPI dependency: lease a connection and return it on request end.

    Always rollback before returning so the connection never goes back to the
    pool with an uncommitted or aborted transaction (which would surface as
    InFailedSqlTransaction for the next user). Rollback after a successful
    commit is a no-op and harmless.
    """
    pool_ref = _require_pool()
    conn = pool_ref.getconn()
    try:
        yield conn
    finally:
        try:
            conn.rollback()
        except Exception:
            logger.exception("Rollback failed while returning connection to pool")
        pool_ref.putconn(conn)


def get_connection():
    """Background-task helper: lease a connection. The caller must call
    release_connection() to return it to the pool."""
    return _require_pool().getconn()


def release_connection(conn):
    """Return a connection to the pool. Rolls back first, mirroring get_db()."""
    try:
        conn.rollback()
    except Exception:
        logger.exception("Rollback failed while releasing background-task connection")
    _require_pool().putconn(conn)


if __name__ == "__main__":
    import sys

    if "--init" in sys.argv:
        from app.init_db import initialize_database
        from app.shared.infrastructure.logger import setup_logger

        setup_logger()
        try:
            initialize_database()
            print("[OK] Database initialization complete")
        except Exception as e:
            print(f"[ERROR] Database initialization failed: {e}")
            sys.exit(1)
    else:
        print("Usage: python -m app.shared.infrastructure.database --init")
        sys.exit(1)
