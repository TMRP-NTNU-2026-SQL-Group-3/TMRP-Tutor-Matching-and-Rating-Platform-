"""Application-level orchestration for admin CSV/ZIP import/export and reset.

The router layer should only: (1) parse the HTTP upload, (2) call these
methods, (3) shape the ApiResponse. All table-ordering, transaction, and
row-level error handling lives here or in the infrastructure layer below."""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

from app.admin.domain.tables import (
    ALLOWED_TABLES,
    DELETE_ORDER,
    EXPORTABLE_TABLES,
    IMPORT_ORDER,
    validate_exportable_table,
    validate_table,
)
from app.admin.infrastructure.csv_io import parse_csv, write_csv
from app.admin.infrastructure.table_admin_repo import TableAdminRepository
from app.shared.domain.exceptions import DomainException, NotFoundError
from app.shared.domain.ports import IUnitOfWork
from app.shared.infrastructure.config import settings

try:
    from psycopg2 import errors as _pg_errors
    _FK_VIOLATION = _pg_errors.ForeignKeyViolation
    _UNIQUE_VIOLATION = _pg_errors.UniqueViolation
    _NOT_NULL_VIOLATION = _pg_errors.NotNullViolation
except ImportError:  # pragma: no cover — psycopg2 is a hard runtime dep
    _FK_VIOLATION = _UNIQUE_VIOLATION = _NOT_NULL_VIOLATION = ()


def _format_row_error(exc: Exception) -> str:
    """Turn a raw psycopg2 error into something readable in the admin UI."""
    if _FK_VIOLATION and isinstance(exc, _FK_VIOLATION):
        diag = getattr(exc, "diag", None)
        detail = getattr(diag, "message_detail", None) if diag else None
        return f"外鍵不存在: {detail or exc}".strip()
    if _UNIQUE_VIOLATION and isinstance(exc, _UNIQUE_VIOLATION):
        return "唯一鍵重複"
    if _NOT_NULL_VIOLATION and isinstance(exc, _NOT_NULL_VIOLATION):
        diag = getattr(exc, "diag", None)
        col = getattr(diag, "column_name", None) if diag else None
        return f"欄位不可為 NULL: {col}" if col else "欄位不可為 NULL"
    return str(exc)

logger = logging.getLogger("app.admin")

# Re-exported for back-compat with any import sites that grabbed the constant.
MAX_UPLOAD_SIZE = settings.admin_max_upload_bytes
MAX_IMPORT_ROWS_PER_TABLE = settings.admin_max_import_rows_per_table


class AdminImportService:
    def __init__(self, repo: TableAdminRepository, uow: IUnitOfWork):
        self._repo = repo
        self._uow = uow

    # ── Import ──────────────────────────────────────────────────────

    def import_single_csv(
        self, *, table_name: str, content: bytes | str, upsert: bool = False
    ) -> int:
        """Import one CSV blob into one table. Returns row count written.

        When `upsert=True` rows are merged by primary key (existing rows are
        updated, new rows are inserted). The default plain-INSERT mode raises on
        any PK conflict.
        """
        validate_table(table_name)
        # SEC-10: null bytes are a reliable binary-file indicator; reject before
        # the UTF-8 decode so the CSV parser never sees non-text input.
        if isinstance(content, (bytes, bytearray)) and b"\x00" in content[:512]:
            raise DomainException("上傳的檔案不是有效的 CSV（偵測到二進位內容）", 415)
        text = content.decode("utf-8-sig") if isinstance(content, (bytes, bytearray)) else content
        rows = parse_csv(text)
        if not rows:
            return 0
        if len(rows) > MAX_IMPORT_ROWS_PER_TABLE:
            raise DomainException(f"超過單表匯入上限 {MAX_IMPORT_ROWS_PER_TABLE} 筆")
        columns = list(rows[0].keys())
        self._assert_columns_in_schema(table_name, columns)
        with self._uow.begin():
            if upsert:
                pk_cols = self._repo.get_primary_key_columns(table_name)
                for row in rows:
                    self._repo.upsert_csv_row(table_name, columns, [row[c] for c in columns], pk_cols)
            else:
                for row in rows:
                    self._repo.insert_csv_row(table_name, columns, [row[c] for c in columns])
            self._repo.reset_serial_sequences([table_name])
        return len(rows)

    def _assert_columns_in_schema(self, table_name: str, columns: list[str]) -> None:
        """B9: reject CSV headers referencing columns the target table does
        not have. The identifier regex in `insert_csv_row` only proves the
        name is syntactically safe to splice; it does not prove the column
        exists. Without this check, an unknown column reaches psycopg2 and
        surfaces a schema-leaking error back to the admin UI."""
        existing = self._repo.get_schema_columns(table_name)
        unknown = [c for c in columns if c not in existing]
        if unknown:
            raise DomainException(
                f"CSV 標頭包含 {table_name} 不存在的欄位：{', '.join(unknown)}"
            )

    def import_zip(
        self,
        *,
        zip_bytes: bytes,
        admin_user_id: int,
        clear_first: bool,
        upsert: bool = False,
    ) -> dict:
        """Import a ZIP containing one CSV per whitelisted table.

        `clear_first=True` (overwrite mode) truncates all tables before writing.
        `upsert=True` merges rows by primary key without truncating first.
        The two modes are mutually exclusive.

        Uses per-row SAVEPOINTs so one bad row does not abort the whole table.
        Returns a dict with `imported` counts and optional `errors` details.
        """
        if clear_first and upsert:
            raise DomainException("clear_first 與 upsert 模式互斥，請擇一使用")
        if len(zip_bytes) > MAX_UPLOAD_SIZE:
            raise DomainException(f"上傳檔案過大（上限 {MAX_UPLOAD_SIZE // 1024 // 1024} MB）")
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        except zipfile.BadZipFile as e:
            raise DomainException("上傳的檔案不是有效的 ZIP 壓縮檔") from e

        csv_files = {}
        for name in zf.namelist():
            if name.endswith(".csv"):
                table_name = Path(name).stem
                if table_name in ALLOWED_TABLES:
                    csv_files[table_name] = name
        if not csv_files:
            raise DomainException("ZIP 檔案中沒有找到任何可匯入的 CSV 檔案")

        result: dict[str, int] = {}
        errors: dict[str, list[str]] = {}

        with self._uow.begin():
            if clear_first:
                self._reset_tables(admin_user_id)
            for table in IMPORT_ORDER:
                if table not in csv_files:
                    continue
                csv_content = zf.read(csv_files[table]).decode("utf-8-sig")
                rows = parse_csv(csv_content)
                if not rows:
                    result[table] = 0
                    continue
                if len(rows) > MAX_IMPORT_ROWS_PER_TABLE:
                    errors[table] = [f"超過單表匯入上限 {MAX_IMPORT_ROWS_PER_TABLE} 筆"]
                    continue
                columns = list(rows[0].keys())
                try:
                    self._assert_columns_in_schema(table, columns)
                except DomainException as e:
                    errors[table] = [str(e)]
                    continue
                inserted = 0
                table_errors: list[str] = []
                pk_cols = self._repo.get_primary_key_columns(table) if upsert else []
                for i, row in enumerate(rows, 1):
                    # The counter must only advance after the savepoint is
                    # released — an INSERT that succeeds but whose savepoint
                    # release later fails is not a committed row, and the
                    # outer transaction will roll it back. Incrementing
                    # earlier produced a misleading "inserted" total.
                    self._repo.savepoint()
                    try:
                        if upsert:
                            self._repo.upsert_csv_row(table, columns, [row[c] for c in columns], pk_cols)
                        else:
                            self._repo.insert_csv_row(table, columns, [row[c] for c in columns])
                    except Exception as e:
                        self._repo.rollback_to_savepoint()
                        table_errors.append(f"第 {i} 列: {_format_row_error(e)}")
                    else:
                        self._repo.release_savepoint()
                        inserted += 1
                result[table] = inserted
                if table_errors:
                    errors[table] = table_errors
            self._repo.reset_serial_sequences(list(result.keys()))

        return {"imported": result, "errors": errors}

    # ── Reset ───────────────────────────────────────────────────────

    def reset_database(self, *, admin_user_id: int) -> dict[str, int]:
        """Delete all data (respecting FK order) except the calling admin user."""
        deleted: dict[str, int] = {}
        with self._uow.begin():
            for table in DELETE_ORDER:
                before = self._repo.count(table)
                if table == "users":
                    self._repo.delete_users_except(admin_user_id)
                    after = self._repo.count(table)
                    deleted[table] = before - after
                else:
                    self._repo.delete_all(table)
                    deleted[table] = before
        return deleted

    def _reset_tables(self, admin_user_id: int) -> None:
        for table in DELETE_ORDER:
            if table == "users":
                self._repo.delete_users_except(admin_user_id)
            else:
                self._repo.delete_all(table)

    # ── Export ──────────────────────────────────────────────────────

    def export_table_to_csv(self, *, table_name: str, export_dir: Path) -> Path:
        validate_exportable_table(table_name)
        rows = self._repo.select_all(table_name)
        if not rows:
            raise NotFoundError(f"{table_name} 無資料可匯出")
        export_dir.mkdir(parents=True, exist_ok=True)
        path = export_dir / f"{table_name}.csv"
        write_csv(str(path), rows)
        return path

    def export_all_tables_to_zip(
        self,
        *,
        export_dir: Path,
        zip_name: str = "all_tables.zip",
        include_sensitive: bool = False,
    ) -> Path:
        """Export every non-empty allowed table to a ZIP.

        ``include_sensitive`` controls whether tables on the EXPORT_DENYLIST
        (notably ``users`` with its password_hash column) are included. The
        HTTP ``/admin/export-all`` endpoint leaves it False so downloadable
        archives cannot leak credential material. The pre-reset DR backup
        passes True because the archive is written to a server-local path
        and a reset without users is not actually restorable.
        """
        export_dir.mkdir(parents=True, exist_ok=True)
        exported: list[Path] = []
        tables = ALLOWED_TABLES if include_sensitive else EXPORTABLE_TABLES
        zip_path = export_dir / zip_name
        # Any partial CSV written before an error must be cleaned up, otherwise
        # repeated admin/reset failures accumulate orphan artefacts on disk
        # (and can leak sensitive column data for aborted include_sensitive
        # runs). Wrap the loop so the finally block fires on success and
        # failure alike — the CSVs are intermediate, only the zip is the
        # deliverable.
        try:
            for table in sorted(tables):
                rows = self._repo.select_all(table)
                if rows:
                    path = export_dir / f"{table}.csv"
                    write_csv(str(path), rows)
                    exported.append(path)
            if not exported:
                raise NotFoundError("所有資料表均無資料可匯出")
            with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
                for csv_path in exported:
                    zf.write(str(csv_path), csv_path.name)
        except Exception:
            # Remove a half-written zip so callers don't mistake a truncated
            # archive for a valid backup.
            try:
                if zip_path.exists():
                    zip_path.unlink()
            except OSError:
                pass
            raise
        finally:
            for csv_path in exported:
                try:
                    csv_path.unlink()
                except OSError:
                    pass
        return zip_path
