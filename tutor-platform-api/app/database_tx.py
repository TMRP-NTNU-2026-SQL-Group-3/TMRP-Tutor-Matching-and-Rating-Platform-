from contextlib import contextmanager


@contextmanager
def transaction(conn):
    """
    交易管理上下文管理器。

    Usage:
        with transaction(conn):
            repo.create(...)
            repo.update(...)

    成功時自動 commit，例外時自動 rollback。
    """
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = True
