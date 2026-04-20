from app.shared.domain.exceptions import DomainException


# Order tables must be deleted in to respect foreign-key constraints.
# Treated as the single source of truth for which tables admin endpoints
# may operate on. Reverse this for import ordering.
DELETE_ORDER: tuple[str, ...] = (
    "session_edit_logs", "messages", "conversations", "reviews", "exams",
    "sessions", "matches", "tutor_availability", "tutor_subjects",
    "students", "tutors", "subjects", "users",
)

IMPORT_ORDER: tuple[str, ...] = tuple(reversed(DELETE_ORDER))

# Derived from DELETE_ORDER so any schema change only needs to update
# the ordering tuple — the allow-list stays consistent automatically.
ALLOWED_TABLES: frozenset[str] = frozenset(DELETE_ORDER)

# Tables that are never included in CSV/ZIP exports. `users` rows contain
# password_hash and are therefore excluded from export even though admin
# import still needs to handle them. Anyone with the admin role holding the
# users export would effectively hold an offline-crackable credential dump.
EXPORT_DENYLIST: frozenset[str] = frozenset({"users"})

EXPORTABLE_TABLES: frozenset[str] = ALLOWED_TABLES - EXPORT_DENYLIST


def validate_table(table_name: str) -> str:
    if table_name not in ALLOWED_TABLES:
        raise DomainException(f"不允許的資料表名稱：{table_name}")
    return table_name


def validate_exportable_table(table_name: str) -> str:
    """Stricter check for export endpoints — keeps password_hash out of
    downloadable artefacts even when the caller is an admin."""
    validate_table(table_name)
    if table_name not in EXPORTABLE_TABLES:
        raise DomainException(f"不允許匯出的資料表：{table_name}")
    return table_name
