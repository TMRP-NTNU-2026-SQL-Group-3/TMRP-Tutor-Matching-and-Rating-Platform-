"""CSV import/export column helpers used by admin table operations.

These helpers cover admin-specific CSV-shaped flows (bulk INSERT from CSV rows).
Identifier quoting is now handled by `psycopg2.sql.Identifier` at the call
site; the generic identifier-syntax check still lives in
`shared.infrastructure.column_validation`.
"""

from app.shared.infrastructure.column_validation import (
    validate_column_name,
    validate_columns,
)

__all__ = ["coerce_csv_value", "validate_column_name", "validate_columns"]


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
