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

    Callers are responsible for committing the surrounding transaction.
    """
    cursor.execute(
        "INSERT INTO password_history (user_id, password_hash) VALUES (%s, %s)",
        (user_id, password_hash),
    )
    cursor.execute(
        "DELETE FROM password_history "
        "WHERE user_id = %s AND history_id NOT IN ("
        "  SELECT history_id FROM password_history "
        "  WHERE user_id = %s ORDER BY changed_at DESC LIMIT %s"
        ")",
        (user_id, user_id, _HISTORY_LIMIT),
    )
