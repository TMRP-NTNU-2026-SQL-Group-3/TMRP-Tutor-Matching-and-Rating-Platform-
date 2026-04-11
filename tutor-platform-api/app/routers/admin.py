import csv
import io
import logging
import re
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse

from app.config import settings
from app.database_tx import transaction
from app.dependencies import get_db, require_role
from app.exceptions import AppException, NotFoundException
from app.models.common import ApiResponse
from app.repositories.base import BaseRepository
from app.utils.columns import quote_columns, coerce_csv_value, validate_columns
from app.utils.csv_handler import write_csv

logger = logging.getLogger("app.admin")

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_IMPORT_ROWS_PER_TABLE = 50_000


def _safe_validate_columns(columns: list[str]) -> None:
    """包裝 validate_columns，將 ValueError 轉為 AppException（回傳 400 而非 500）。"""
    try:
        validate_columns(columns)
    except ValueError as e:
        raise AppException(str(e)) from e

router = APIRouter(prefix="/api/admin", tags=["admin"])

ALLOWED_TABLES = {
    "users",
    "students",
    "tutors",
    "subjects",
    "tutor_subjects",
    "tutor_availability",
    "matches",
    "sessions",
    "session_edit_logs",
    "exams",
    "reviews",
    "conversations",
    "messages",
}

# 清空資料庫時的刪除順序（先刪子表，再刪父表）
_DELETE_ORDER = [
    "session_edit_logs",
    "messages",
    "conversations",
    "reviews",
    "exams",
    "sessions",
    "matches",
    "tutor_availability",
    "tutor_subjects",
    "students",
    "tutors",
    "subjects",
    "users",
]


def _validate_table(table_name: str) -> str:
    """驗證資料表名稱是否在允許清單中。"""
    if table_name not in ALLOWED_TABLES:
        raise AppException(f"不允許的資料表名稱：{table_name}")
    return table_name


def _reset_serial_sequences(cursor, table_names: list[str]) -> None:
    """重置指定資料表的 SERIAL 序列，使其與目前最大 ID 對齊。

    CSV 匯入帶有明確主鍵值的資料後，若不重置序列，
    後續 INSERT 產生的 ID 可能與已有資料衝突（UniqueViolation）。
    """
    for table in table_names:
        cursor.execute(
            "SELECT column_name, pg_get_serial_sequence(%s, column_name) AS seq "
            "FROM information_schema.columns "
            "WHERE table_name = %s AND column_default LIKE 'nextval%%'",
            (table, table),
        )
        for row in cursor.fetchall():
            col_name, seq_name = row[0], row[1]
            if seq_name:
                cursor.execute(
                    f"SELECT setval('{seq_name}', COALESCE((SELECT MAX(\"{col_name}\") FROM {table}), 0) + 1, false)"
                )


# ---------- 1. 使用者列表 ----------

@router.get("/users", summary="使用者列表", description="列出系統中所有使用者的基本資料。僅限管理員。", response_model=ApiResponse)
def list_users(user=Depends(require_role("admin")), conn=Depends(get_db)):
    repo = BaseRepository(conn)
    rows = repo.fetch_all(
        "SELECT user_id, username, role, display_name, phone, email, created_at "
        "FROM users ORDER BY user_id"
    )
    return ApiResponse(success=True, data=rows, message=f"共 {len(rows)} 位使用者")


# ---------- 2. 假資料生成 ----------

@router.post("/seed", summary="生成假資料", description="呼叫假資料產生器，為系統填入測試用資料。若已有資料則可能跳過。僅限管理員。", response_model=ApiResponse)
def seed_data(user=Depends(require_role("admin")), conn=Depends(get_db)):
    logger.warning("Admin user_id=%s 執行假資料生成", user.get("sub"))
    from seed.generator import run_seed

    result = run_seed(conn)
    if result.get("skipped"):
        return ApiResponse(success=True, data=result, message=result.get("message", "已跳過"))
    total = sum(v for v in result.values() if isinstance(v, int))
    return ApiResponse(success=True, data=result, message=f"已產生 {total} 筆假資料")


# ---------- 3. CSV 匯入 ----------

@router.post("/import", summary="匯入 CSV", description="上傳 CSV 檔案匯入指定資料表。欄位名稱需符合安全規範。僅限管理員。", response_model=ApiResponse)
def import_csv(
    file: UploadFile = File(...),
    table_name: str = Query(..., description="目標資料表名稱"),
    user=Depends(require_role("admin")),
    conn=Depends(get_db),
):
    _validate_table(table_name)
    logger.warning("Admin user_id=%s 匯入 CSV 至 %s", user.get("sub"), table_name)

    content = file.file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)

    if not rows:
        return ApiResponse(success=True, data={"count": 0}, message="CSV 檔案無資料列")

    # Strip whitespace from header names (csv.DictReader preserves it)
    rows = [{h.strip(): v for h, v in row.items()} for row in rows]
    columns = list(rows[0].keys())
    _safe_validate_columns(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    col_names = quote_columns(columns)
    sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})"

    cursor = conn.cursor()
    try:
        for row in rows:
            values = tuple(coerce_csv_value(row[c]) for c in columns)
            cursor.execute(sql, values)
        _reset_serial_sequences(cursor, [table_name])
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return ApiResponse(
        success=True,
        data={"count": len(rows)},
        message=f"已匯入 {len(rows)} 筆資料至 {table_name}",
    )


# ---------- 4. CSV 匯出 ----------

@router.get("/export/{table_name}", summary="匯出 CSV", description="將指定資料表的所有資料匯出為 CSV 檔案下載。僅限管理員。")
def export_csv(
    table_name: str,
    user=Depends(require_role("admin")),
    conn=Depends(get_db),
):
    _validate_table(table_name)
    logger.warning("Admin user_id=%s 匯出 CSV: %s", user.get("sub"), table_name)

    repo = BaseRepository(conn)
    rows = repo.fetch_all(f"SELECT * FROM {table_name}")

    if not rows:
        raise NotFoundException(f"{table_name} 無資料可匯出")

    export_dir = Path("data/export")
    export_dir.mkdir(parents=True, exist_ok=True)
    export_path = export_dir / f"{table_name}.csv"
    write_csv(str(export_path), rows)

    safe_filename = re.sub(r'[^A-Za-z0-9_\-]', '', table_name) + ".csv"
    return FileResponse(
        path=str(export_path),
        filename=safe_filename,
        media_type="text/csv",
    )


# ---------- 5. 清空資料庫 ----------

@router.post("/reset", summary="清空資料庫", description="刪除所有資料（保留管理員帳號與表結構）。需傳入 confirm=true 確認操作。僅限管理員。", response_model=ApiResponse)
def reset_database(
    confirm: bool = Query(..., description="必須傳入 true 以確認操作"),
    user=Depends(require_role("admin")),
    conn=Depends(get_db),
):
    if not confirm:
        raise AppException("請傳入 confirm=true 以確認清空資料庫")

    logger.warning("Admin user_id=%s 執行清空資料庫", user.get("sub"))
    repo = BaseRepository(conn)
    cursor = conn.cursor()
    admin_user_id = int(user["sub"])
    deleted = {}

    try:
        for table in _DELETE_ORDER:
            if table == "users":
                # 保留目前操作的 Admin 帳號
                rows_before = repo.fetch_one(f"SELECT COUNT(*) AS cnt FROM {table}")
                cursor.execute(f"DELETE FROM {table} WHERE user_id <> %s", (admin_user_id,))
                rows_after = repo.fetch_one(f"SELECT COUNT(*) AS cnt FROM {table}")
                deleted[table] = (rows_before["cnt"] or 0) - (rows_after["cnt"] or 0)
            else:
                rows = repo.fetch_one(f"SELECT COUNT(*) AS cnt FROM {table}")
                cursor.execute(f"DELETE FROM {table}")
                deleted[table] = rows["cnt"] or 0
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    total = sum(deleted.values())
    return ApiResponse(
        success=True,
        data=deleted,
        message=f"已刪除 {total} 筆資料，Admin 帳號已保留",
    )


# ---------- 6. 系統狀態 ----------

@router.get("/system-status", summary="系統狀態", description="查詢各資料表的筆數、使用者角色分布、配對狀態分布等系統統計資訊。僅限管理員。", response_model=ApiResponse)
def system_status(user=Depends(require_role("admin")), conn=Depends(get_db)):
    repo = BaseRepository(conn)

    counts = {}
    for table in ALLOWED_TABLES:
        row = repo.fetch_one(f"SELECT COUNT(*) AS cnt FROM {table}")
        counts[table] = row["cnt"] or 0

    role_counts = repo.fetch_all(
        "SELECT role, COUNT(*) AS cnt FROM users GROUP BY role"
    )
    roles = {r["role"]: r["cnt"] for r in role_counts}

    status_counts = repo.fetch_all(
        "SELECT status, COUNT(*) AS cnt FROM matches GROUP BY status"
    )
    match_statuses = {r["status"]: r["cnt"] for r in status_counts}

    return ApiResponse(
        success=True,
        data={
            "table_counts": counts,
            "role_counts": roles,
            "match_statuses": match_statuses,
        },
        message="系統狀態查詢完成",
    )


# ---------- 7. 一鍵匯出全部資料表 ----------

@router.post("/export-all", summary="一鍵匯出全部", description="將所有資料表匯出為 CSV 並打包成 ZIP 下載。僅限管理員。")
def export_all(user=Depends(require_role("admin")), conn=Depends(get_db)):
    logger.warning("Admin user_id=%s 執行一鍵匯出全部資料表", user.get("sub"))
    repo = BaseRepository(conn)
    export_dir = Path("data/export")
    export_dir.mkdir(parents=True, exist_ok=True)

    exported_tables = []
    for table in sorted(ALLOWED_TABLES):
        rows = repo.fetch_all(f"SELECT * FROM {table}")
        if rows:
            csv_path = export_dir / f"{table}.csv"
            write_csv(str(csv_path), rows)
            exported_tables.append(csv_path)

    if not exported_tables:
        raise NotFoundException("所有資料表均無資料可匯出")

    zip_path = export_dir / "all_tables.zip"
    with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
        for csv_path in exported_tables:
            zf.write(str(csv_path), csv_path.name)

    return FileResponse(
        path=str(zip_path),
        filename="all_tables.zip",
        media_type="application/zip",
    )


# ---------- 8. 背景任務狀態查詢 ----------

@router.get("/tasks/{task_id}", summary="查詢背景任務", description="查詢 Huey 背景任務的執行狀態（pending / completed / failed）。僅限管理員。", response_model=ApiResponse)
def get_task_status(
    task_id: str,
    user=Depends(require_role("admin")),
):
    from app.worker import huey as huey_instance

    try:
        raw = huey_instance.storage.peek_data(task_id)
    except Exception:
        return ApiResponse(success=True, data={"task_id": task_id, "status": "pending"})

    if raw is huey_instance.EmptyData:
        return ApiResponse(success=True, data={"task_id": task_id, "status": "pending"})

    try:
        import json
        result = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Fallback: try pickle for legacy data, but prefer JSON going forward
        try:
            import pickle  # nosec B301 — admin-only, legacy Huey SQLite storage
            result = pickle.loads(raw)  # nosec B301
        except Exception:
            result = None

    if isinstance(result, Exception):
        return ApiResponse(success=True, data={
            "task_id": task_id,
            "status": "failed",
            "error": str(result),
        })

    return ApiResponse(success=True, data={
        "task_id": task_id,
        "status": "completed",
        "result": result,
    })


# ---------- 9. 一鍵匯入全部資料表 ----------

# 匯入順序：先父表再子表（_DELETE_ORDER 的反序）
_IMPORT_ORDER = list(reversed(_DELETE_ORDER))


@router.post("/import-all", summary="一鍵匯入全部", description="上傳 ZIP 檔案（內含各表 CSV），一次匯入所有資料表。可選擇匯入前先清空。僅限管理員。", response_model=ApiResponse)
def import_all(
    file: UploadFile = File(...),
    clear_first: bool = Query(False, description="匯入前先清空資料表"),
    user=Depends(require_role("admin")),
    conn=Depends(get_db),
):
    content = file.file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise AppException(f"上傳檔案過大（上限 {MAX_UPLOAD_SIZE // 1024 // 1024} MB）")
    buf = io.BytesIO(content)

    try:
        zf = zipfile.ZipFile(buf)
    except zipfile.BadZipFile:
        raise AppException("上傳的檔案不是有效的 ZIP 壓縮檔")

    # 解析 ZIP 中的 CSV 檔案名稱 → 對應資料表
    csv_files = {}
    for name in zf.namelist():
        if name.endswith(".csv"):
            table_name = Path(name).stem
            if table_name in ALLOWED_TABLES:
                csv_files[table_name] = name

    if not csv_files:
        raise AppException("ZIP 檔案中沒有找到任何可匯入的 CSV 檔案")

    cursor = conn.cursor()
    result = {}
    errors = {}

    logger.warning("Admin user_id=%s 執行一鍵匯入 (clear_first=%s)", user.get("sub"), clear_first)

    with transaction(conn):
        if clear_first:
            admin_user_id = int(user["sub"])
            for table in _DELETE_ORDER:
                if table == "users":
                    cursor.execute(f"DELETE FROM {table} WHERE user_id <> %s", (admin_user_id,))
                else:
                    cursor.execute(f"DELETE FROM {table}")

        for table in _IMPORT_ORDER:
            if table not in csv_files:
                continue
            csv_content = zf.read(csv_files[table]).decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(csv_content))
            rows = list(reader)
            if not rows:
                result[table] = 0
                continue
            if len(rows) > MAX_IMPORT_ROWS_PER_TABLE:
                errors[table] = [f"超過單表匯入上限 {MAX_IMPORT_ROWS_PER_TABLE} 筆"]
                continue

            # Strip whitespace from header names (csv.DictReader preserves it)
            rows = [{h.strip(): v for h, v in row.items()} for row in rows]
            columns = list(rows[0].keys())
            _safe_validate_columns(columns)
            placeholders = ", ".join(["%s"] * len(columns))
            col_names = quote_columns(columns)
            sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"

            table_errors = []
            inserted = 0
            for i, row in enumerate(rows, 1):
                values = tuple(coerce_csv_value(row[c]) for c in columns)
                try:
                    cursor.execute("SAVEPOINT row_sp")
                    cursor.execute(sql, values)
                    cursor.execute("RELEASE SAVEPOINT row_sp")
                    inserted += 1
                except Exception as e:
                    cursor.execute("ROLLBACK TO SAVEPOINT row_sp")
                    table_errors.append(f"第 {i} 列: {e}")

            result[table] = inserted
            if table_errors:
                errors[table] = table_errors

        # 重置所有已匯入資料表的 SERIAL 序列
        _reset_serial_sequences(cursor, list(result.keys()))

    total = sum(result.values())
    data = {"imported": result}
    if errors:
        data["errors"] = errors
    return ApiResponse(
        success=True,
        data=data,
        message=f"已匯入 {total} 筆資料（{len(result)} 張表）" + (f"，{sum(len(v) for v in errors.values())} 筆失敗" if errors else ""),
    )
