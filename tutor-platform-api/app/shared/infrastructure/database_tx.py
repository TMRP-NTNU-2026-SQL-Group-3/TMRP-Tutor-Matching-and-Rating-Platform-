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
    支援巢狀呼叫——若已在交易中，僅穿透 yield，由最外層負責 commit/rollback。

    使用連線物件的 _in_tx 屬性追蹤交易狀態，取代舊版的全域 set + id(conn)，
    避免 ThreadedConnectionPool 下多執行緒的競態條件。

    Bug #9：用 try/finally 結構分離「巢狀穿透」與「外層提交」邏輯，
    避免維護者誤刪 return 而導致在巢狀情境下重複 commit/rollback。
    """
    is_outermost = not getattr(conn, '_in_tx', False)

    if not is_outermost:
        # 已在外層交易中，僅穿透 yield；不在此處 commit/rollback
        yield conn
        return

    conn._in_tx = True
    try:
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
    finally:
        conn._in_tx = False
