import threading
from contextlib import contextmanager

# DB-L03: Track transaction state in a thread-safe dict keyed by
# connection id, instead of monkey-patching `_in_tx` onto the
# connection object. This avoids AttributeError on connection
# wrappers / proxies that use __slots__ or restrict attribute assignment.
_tx_state: dict[int, bool] = {}
_tx_lock = threading.Lock()


def _is_in_tx(conn) -> bool:
    return _tx_state.get(id(conn), False)


def _set_in_tx(conn, value: bool) -> None:
    with _tx_lock:
        if value:
            _tx_state[id(conn)] = True
        else:
            _tx_state.pop(id(conn), None)


@contextmanager
def transaction(conn):
    """Transaction context manager.

    Usage:
        with transaction(conn):
            repo.create(...)
            repo.update(...)

    Auto-commits on success, auto-rollbacks on exception.
    Supports nesting — if already inside a transaction, yields through
    without commit/rollback; the outermost layer owns the lifecycle.

    Transaction state is tracked in a thread-safe dict keyed by
    ``id(conn)`` so arbitrary attribute assignment on the connection
    object is not required.

    Bug #9: try/finally separates "nested pass-through" from "outer
    commit" logic so an accidental return deletion does not cause
    duplicate commit/rollback in nested scenarios.
    """
    is_outermost = not _is_in_tx(conn)

    if not is_outermost:
        yield conn
        return

    _set_in_tx(conn, True)
    try:
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
    finally:
        _set_in_tx(conn, False)
