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
    不支援巢狀使用——若已在交易中，直接 yield 不做額外 commit/rollback。

    使用連線物件的 _in_tx 屬性追蹤交易狀態，取代舊版的全域 set + id(conn)，
    避免 ThreadedConnectionPool 下多執行緒的競態條件。
    """
    if getattr(conn, '_in_tx', False):
        # 已在外層交易中，直接穿透，由外層管理 commit/rollback
        yield conn
        return

    conn._in_tx = True
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn._in_tx = False
