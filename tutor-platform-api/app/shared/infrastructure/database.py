import logging
import threading

import psycopg2
from psycopg2 import pool

from app.shared.infrastructure.config import settings

logger = logging.getLogger("app.db")

_pool: pool.ThreadedConnectionPool | None = None
_rl_pool: pool.ThreadedConnectionPool | None = None
# Guards init_pool()/close_pool() so the FastAPI lifespan and the Huey worker
# startup hook can both call them without racing on the module globals.
_pool_lock = threading.Lock()

_TCP_KEEPALIVE_OPTS = dict(keepalives=1, keepalives_idle=60, keepalives_interval=10, keepalives_count=3)


def init_pool():
    """Initialize the PostgreSQL connection pool. Call once at app startup.

    Idempotent and thread-safe: a call made while a pool already exists is a
    no-op. Both the FastAPI lifespan and the Huey worker's on_startup hook
    call this — the worker runs in a separate process from the API, so it must
    open its own pool, and the guard below stops a second worker thread from
    leaking a duplicate pool.
    """
    global _pool, _rl_pool
    with _pool_lock:
        if _pool is not None:
            return
        _pool = pool.ThreadedConnectionPool(
            minconn=settings.db_pool_min,
            maxconn=settings.db_pool_max,
            dsn=settings.database_url,
            **_TCP_KEEPALIVE_OPTS,
        )
        # M-08: dedicated pool for rate-limit middleware so its DB checks do not
        # compete with handler connections from the main pool. Cap is sized to
        # match expected concurrent rate-limit checks (one per inbound request +
        # per-username/per-action sub-buckets) so a burst does not exhaust the
        # rl pool and force sensitive endpoints (login) into fail-closed mode,
        # which would surface to legitimate users as spurious 429s.
        _rl_pool = pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=max(10, settings.db_pool_max // 2),
            dsn=settings.database_url,
            **_TCP_KEEPALIVE_OPTS,
        )


def close_pool():
    """Close the connection pool. Call at app shutdown."""
    global _pool, _rl_pool
    with _pool_lock:
        if _pool:
            _pool.closeall()
            _pool = None
        if _rl_pool:
            _rl_pool.closeall()
            _rl_pool = None


def _require_pool() -> pool.ThreadedConnectionPool:
    """Return the pool, or raise if init_pool() was never called."""
    if _pool is None:
        raise RuntimeError(
            "Database pool not initialized. Call init_pool() first, or make "
            "sure the app is launched through its lifespan (not by importing "
            "modules in isolation)."
        )
    return _pool


def _require_rl_pool() -> pool.ThreadedConnectionPool:
    """Return the rate-limit pool, falling back to the main pool."""
    return _rl_pool if _rl_pool is not None else _require_pool()


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


def pool_stats() -> dict:
    """Snapshot of pool utilisation for operator visibility (I-13).

    psycopg2's ThreadedConnectionPool does not expose a public stats API,
    so we read the internal structures under its lock. Values are a
    point-in-time snapshot — "in_use" may change the moment we return.
    """
    p = _require_pool()
    try:
        with p._lock:  # noqa: SLF001 — no public accessor
            total = len(p._used) + len(p._pool)
            return {
                "min": p.minconn,
                "max": p.maxconn,
                "in_use": len(p._used),
                "idle": len(p._pool),
                "total": total,
                "utilization": round(len(p._used) / p.maxconn, 3) if p.maxconn else 0.0,
            }
    except AttributeError:
        return {"min": p.minconn, "max": p.maxconn, "error": "pool internals unavailable"}


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
