from contextlib import contextmanager

# 追蹤連線是否已在交易中，防止巢狀交易導致提前 commit
_in_transaction = set()


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
    """
    conn_id = id(conn)
    if conn_id in _in_transaction:
        # 已在外層交易中，直接穿透，由外層管理 commit/rollback
        yield conn
        return

    _in_transaction.add(conn_id)
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _in_transaction.discard(conn_id)
        conn.autocommit = True
