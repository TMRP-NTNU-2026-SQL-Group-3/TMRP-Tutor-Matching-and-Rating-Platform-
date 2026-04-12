import csv
import io
import logging
from pathlib import Path

from app.admin.domain.tables import ALLOWED_TABLES
from app.shared.infrastructure.config import settings
from app.shared.infrastructure.database import get_connection, release_connection
from app.admin.infrastructure.csv_utils import coerce_csv_value, quote_columns
from app.shared.infrastructure.base_repository import BaseRepository
from app.shared.infrastructure.column_validation import validate_column_name
from app.utils.csv_handler import write_csv
from app.worker import huey

logger = logging.getLogger("app.tasks.import_export")


@huey.task(retries=3, retry_delay=10)
def import_csv_task(table_name: str, csv_content: str) -> dict:
    """非同步匯入 CSV 至指定資料表。"""
    if table_name not in ALLOWED_TABLES:
        return {"error": f"不允許的資料表名稱：{table_name}"}

    logger.info("開始匯入 %s", table_name)
    conn = get_connection()
    try:
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)
        if not rows:
            return {"table": table_name, "count": 0}

        # Strip whitespace from header names (csv.DictReader preserves it)
        rows = [{h.strip(): v for h, v in row.items()} for row in rows]
        columns = list(rows[0].keys())
        for col in columns:
            if not validate_column_name(col):
                return {"table": table_name, "error": f"不合法的欄位名稱：{col!r}"}
        placeholders = ", ".join(["%s"] * len(columns))
        col_names = quote_columns(columns)
        sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})"

        cursor = conn.cursor()
        try:
            for row in rows:
                values = tuple(coerce_csv_value(row[c]) for c in columns)
                cursor.execute(sql, values)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        logger.info("已匯入 %d 筆資料至 %s", len(rows), table_name)
        return {"table": table_name, "count": len(rows)}
    except Exception:
        logger.exception("匯入 %s 失敗", table_name)
        raise
    finally:
        release_connection(conn)


@huey.task(retries=3, retry_delay=10)
def export_csv_task(table_name: str) -> dict:
    """非同步匯出指定資料表為 CSV。"""
    if table_name not in ALLOWED_TABLES:
        return {"error": f"不允許的資料表名稱：{table_name}"}

    logger.info("開始匯出 %s", table_name)
    conn = get_connection()
    try:
        repo = BaseRepository(conn)
        rows = repo.fetch_all(f"SELECT * FROM {table_name}")

        if not rows:
            return {"table": table_name, "count": 0, "path": None}

        export_dir = Path("data/export")
        export_dir.mkdir(parents=True, exist_ok=True)
        export_path = export_dir / f"{table_name}.csv"
        write_csv(str(export_path), rows)

        logger.info("已匯出 %d 筆資料從 %s", len(rows), table_name)
        return {"table": table_name, "count": len(rows), "path": str(export_path)}
    except Exception:
        logger.exception("匯出 %s 失敗", table_name)
        raise
    finally:
        release_connection(conn)
