"""CSV import/export column helpers used by admin table operations.

These helpers cover admin-specific CSV-shaped flows (bulk INSERT from CSV rows,
quoting PostgreSQL identifiers during dynamic SQL assembly). The generic
identifier-syntax check lives in `shared.infrastructure.column_validation`.
"""

from app.shared.infrastructure.column_validation import (
    validate_column_name,
    validate_columns,
)

__all__ = ["coerce_csv_value", "quote_columns", "validate_column_name", "validate_columns"]


def quote_columns(columns: list[str]) -> str:
    return ", ".join(f'"{col}"' for col in columns)


def coerce_csv_value(val):
    if val is None:
        return None
    if not val or val.strip() == "":
        return None
    if val in ("True", "true"):
        return True
    if val in ("False", "false"):
        return False
    return val
