import csv
import io
import logging
import re
from pathlib import Path

from app.config import settings
from app.database import get_connection
from app.repositories.base import BaseRepository
from app.utils.csv_handler import write_csv
from app.worker import huey

_SAFE_COLUMN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

logger = logging.getLogger("app.tasks.import_export")

ALLOWED_TABLES = {
    "Users", "Students", "Tutors", "Subjects", "Tutor_Subjects",
    "Tutor_Availability", "Matches", "Sessions", "Session_Edit_Logs",
    "Exams", "Reviews", "Conversations", "Messages",
}


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
            if not _SAFE_COLUMN.match(col):
                return {"table": table_name, "error": f"不合法的欄位名稱：{col!r}"}
        placeholders = ", ".join(["?"] * len(columns))
        col_names = ", ".join(columns)
        sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})"

        cursor = conn.cursor()
        for row in rows:
            values = tuple(row[c] for c in columns)
            cursor.execute(sql, values)
        conn.commit()

        logger.info("已匯入 %d 筆資料至 %s", len(rows), table_name)
        return {"table": table_name, "count": len(rows)}
    except Exception as e:
        conn.rollback()
        logger.exception("匯入 %s 失敗", table_name)
        raise
    finally:
        conn.close()


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

        export_dir = Path(settings.access_db_path).parent / "export"
        export_dir.mkdir(parents=True, exist_ok=True)
        export_path = export_dir / f"{table_name}.csv"
        write_csv(str(export_path), rows)

        logger.info("已匯出 %d 筆資料從 %s", len(rows), table_name)
        return {"table": table_name, "count": len(rows), "path": str(export_path)}
    except Exception:
        logger.exception("匯出 %s 失敗", table_name)
        raise
    finally:
        conn.close()
