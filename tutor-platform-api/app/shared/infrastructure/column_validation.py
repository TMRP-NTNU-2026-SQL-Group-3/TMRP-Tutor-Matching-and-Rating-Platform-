"""SQL identifier validation.

Callers that splice identifiers into dynamic SQL must still quote them
(see `quote_columns` in admin CSV utils); this regex is one half of a
two-layer defence, not a licence to string-concat.
"""

import re

_SAFE_COLUMN_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,62}$')


def validate_column_name(col: str) -> bool:
    """Whitelist check for a single SQL identifier (PostgreSQL ≤ 63 chars)."""
    if not isinstance(col, str):
        return False
    return bool(_SAFE_COLUMN_NAME.match(col))


def validate_columns(columns: list[str], allowed: set[str] | None = None) -> None:
    """Raise ValueError if any column is syntactically invalid or not in the allow-list."""
    for col in columns:
        if not validate_column_name(col):
            raise ValueError(f"不合法的欄位名稱：{col!r}")
        if allowed is not None and col not in allowed:
            raise ValueError(f"不允許更新的欄位：{col!r}")
