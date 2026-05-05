import csv
import io
import logging
from pathlib import Path

from psycopg2 import sql

from app.admin.domain.tables import ALLOWED_TABLES
from app.shared.infrastructure.database import get_connection, release_connection
from app.admin.infrastructure.csv_utils import coerce_csv_value
from app.shared.infrastructure.base_repository import BaseRepository
from app.shared.infrastructure.column_validation import validate_column_name
from app.utils.csv_handler import write_csv
from app.worker import huey

logger = logging.getLogger("app.tasks.import_export")


def _task_extra(request_id: str | None, **fields) -> dict:
    """Bundle structured fields with the originating request_id so worker logs
    can be joined back to the API request that scheduled the task."""
    return {"request_id": request_id or "-", **fields}


@huey.task(retries=3, retry_delay=10, timeout=3600)
def import_csv_task(table_name: str, csv_content: str, admin_user_id: int, request_id: str | None = None) -> dict:
    """Asynchronously import a CSV into the given table.

    `admin_user_id` is verified against the DB so a task enqueued directly
    into huey.db (bypassing the HTTP auth layer) is still rejected if the
    claimed user is not an admin.  `request_id` is propagated from the API
    caller so worker log lines can be correlated with the originating request.
    """
    if table_name not in ALLOWED_TABLES:
        return {"error": f"Disallowed table name: {table_name}"}

    logger.info("Start importing %s", table_name, extra=_task_extra(request_id, table=table_name))
    conn = get_connection()
    try:
        with conn.cursor() as _auth_cur:
            _auth_cur.execute("SELECT role FROM users WHERE user_id = %s", (admin_user_id,))
            _auth_row = _auth_cur.fetchone()
        if not _auth_row or _auth_row[0] != "admin":
            logger.warning(
                "import_csv_task rejected: user_id=%s is not an admin (table=%s)",
                admin_user_id, table_name,
            )
            return {"error": "unauthorized: admin_user_id does not have admin role"}

        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)
        if not rows:
            return {"table": table_name, "count": 0}

        # Strip whitespace from header names (csv.DictReader preserves it)
        rows = [{h.strip(): v for h, v in row.items()} for row in rows]
        columns = list(rows[0].keys())
        for col in columns:
            if not validate_column_name(col):
                return {"table": table_name, "error": f"Invalid column name: {col!r}"}

        # B9: validate column names against the live schema — the regex above
        # only proves the identifier is syntactically safe; an unknown column
        # would otherwise surface a psycopg2 error leaking schema detail.
        cursor = conn.cursor()
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = %s",
            (table_name,),
        )
        existing_cols = {r[0] for r in cursor.fetchall()}
        unknown = [c for c in columns if c not in existing_cols]
        if unknown:
            return {"table": table_name, "error": f"Unknown column(s): {', '.join(unknown)}"}

        col_list = sql.SQL(", ").join(sql.Identifier(c) for c in columns)
        placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in columns)
        insert_stmt = sql.SQL("INSERT INTO {tbl} ({cols}) VALUES ({vals})").format(
            tbl=sql.Identifier(table_name), cols=col_list, vals=placeholders,
        )

        try:
            for row in rows:
                values = tuple(coerce_csv_value(row[c]) for c in columns)
                cursor.execute(insert_stmt, values)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        logger.info(
            "Imported %d rows into %s", len(rows), table_name,
            extra=_task_extra(request_id, table=table_name, rows=len(rows)),
        )
        return {"table": table_name, "count": len(rows)}
    except Exception:
        logger.exception("Import %s failed", table_name, extra=_task_extra(request_id, table=table_name))
        raise
    finally:
        release_connection(conn)


@huey.task(retries=3, retry_delay=10, timeout=3600)
def export_csv_task(table_name: str, admin_user_id: int, request_id: str | None = None) -> dict:
    """Asynchronously export the given table as CSV.

    `admin_user_id` is verified against the DB; see import_csv_task.
    `request_id` is propagated from the API caller; see import_csv_task.
    """
    if table_name not in ALLOWED_TABLES:
        return {"error": f"Disallowed table name: {table_name}"}

    logger.info("Start exporting %s", table_name, extra=_task_extra(request_id, table=table_name))
    conn = get_connection()
    try:
        with conn.cursor() as _auth_cur:
            _auth_cur.execute("SELECT role FROM users WHERE user_id = %s", (admin_user_id,))
            _auth_row = _auth_cur.fetchone()
        if not _auth_row or _auth_row[0] != "admin":
            logger.warning(
                "export_csv_task rejected: user_id=%s is not an admin (table=%s)",
                admin_user_id, table_name,
            )
            return {"error": "unauthorized: admin_user_id does not have admin role"}

        repo = BaseRepository(conn)
        select_stmt = sql.SQL("SELECT * FROM {tbl}").format(tbl=sql.Identifier(table_name))
        rows = repo.fetch_all(select_stmt)

        if not rows:
            return {"table": table_name, "count": 0, "path": None}

        export_dir = Path("data/export")
        export_dir.mkdir(parents=True, exist_ok=True)
        export_path = export_dir / f"{table_name}.csv"
        write_csv(str(export_path), rows)

        logger.info(
            "Exported %d rows from %s", len(rows), table_name,
            extra=_task_extra(request_id, table=table_name, rows=len(rows)),
        )
        return {"table": table_name, "count": len(rows), "path": str(export_path)}
    except Exception:
        logger.exception("Export %s failed", table_name, extra=_task_extra(request_id, table=table_name))
        raise
    finally:
        release_connection(conn)
