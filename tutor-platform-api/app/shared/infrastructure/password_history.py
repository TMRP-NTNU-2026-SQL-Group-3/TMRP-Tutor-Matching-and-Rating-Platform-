"""Shared SQL helper for the password_history table.

Both the identity repo (user-initiated changes) and the admin repo
(admin-initiated resets) write to this table. Keeping the SQL in one
place means a schema change — e.g. widening the trim limit from 5 — is
a single edit rather than a cross-module hunt.
"""

_HISTORY_LIMIT = 5


def save_password_history(cursor, user_id: int, password_hash: str) -> None:
    """Record *password_hash* as the most recent history entry for *user_id*,
    then trim the table so that at most _HISTORY_LIMIT entries are kept.

    Caller must execute within a transaction with at minimum READ COMMITTED
    isolation. Two invariants depend on this:

    1. The INSERT and trim DELETE are a single CTE, so both statements operate
       against the same pre-statement snapshot — the trim cannot see, and
       therefore cannot delete, the newly inserted row. This snapshot guarantee
       is a property of the single statement, not of the isolation level, but
       the statement must execute inside a transaction so that it shares the
       same connection state as the caller's other writes.

    2. Without a surrounding transaction the history INSERT and the caller's
       password_hash UPDATE on users would commit independently. A crash between
       the two would leave the credential changed but history not recorded (or
       vice versa), violating the atomicity the caller relies on.

    Callers are responsible for committing the surrounding transaction.
    """
    # Single CTE so the INSERT and trim DELETE are one atomic statement.
    # PostgreSQL evaluates all CTEs and the main query against the same
    # pre-statement snapshot, so to_keep cannot see the newly inserted row.
    # LIMIT _HISTORY_LIMIT - 1 retains the (_HISTORY_LIMIT - 1) most recent
    # existing rows; the newly inserted row survives because the DELETE's table
    # scan is also bound to the pre-statement snapshot and therefore cannot
    # see it. End result: (_HISTORY_LIMIT - 1) old rows + 1 new = _HISTORY_LIMIT.
    cursor.execute(
        """
        WITH inserted AS (
            INSERT INTO password_history (user_id, password_hash)
            VALUES (%s, %s)
        ),
        to_keep AS (
            SELECT history_id
            FROM password_history
            WHERE user_id = %s
            ORDER BY changed_at DESC
            LIMIT %s
        )
        DELETE FROM password_history
        WHERE user_id = %s
          AND history_id NOT IN (SELECT history_id FROM to_keep)
        """,
        (user_id, password_hash, user_id, _HISTORY_LIMIT - 1, user_id),
    )
