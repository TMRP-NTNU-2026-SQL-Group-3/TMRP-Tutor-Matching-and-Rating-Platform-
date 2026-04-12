import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse

from app.admin.api.dependencies import get_admin_import_service, get_admin_repo
from app.admin.application.import_service import AdminImportService, MAX_UPLOAD_SIZE
from app.admin.domain.tables import ALLOWED_TABLES, validate_table
from app.admin.infrastructure.table_admin_repo import TableAdminRepository
from app.identity.api.dependencies import require_role
from app.shared.api.schemas import ApiResponse
from app.shared.domain.exceptions import DomainException

logger = logging.getLogger("app.admin")

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", summary="使用者列表", response_model=ApiResponse)
def list_users(
    user=Depends(require_role("admin")),
    repo: TableAdminRepository = Depends(get_admin_repo),
):
    rows = repo.list_users()
    return ApiResponse(success=True, data=rows, message=f"共 {len(rows)} 位使用者")


@router.post("/seed", summary="生成假資料", response_model=ApiResponse)
def seed_data(
    user=Depends(require_role("admin")),
    repo: TableAdminRepository = Depends(get_admin_repo),
):
    logger.warning("Admin user_id=%s 執行假資料生成", user.get("sub"))
    from seed.generator import run_seed
    result = run_seed(repo.conn)
    if result.get("skipped"):
        return ApiResponse(success=True, data=result, message=result.get("message", "已跳過"))
    total = sum(v for v in result.values() if isinstance(v, int))
    return ApiResponse(success=True, data=result, message=f"已產生 {total} 筆假資料")


@router.post("/import", summary="匯入 CSV", response_model=ApiResponse)
def import_csv(
    file: UploadFile = File(...),
    table_name: str = Query(...),
    user=Depends(require_role("admin")),
    service: AdminImportService = Depends(get_admin_import_service),
):
    validate_table(table_name)
    logger.warning("Admin user_id=%s 匯入 CSV 至 %s", user.get("sub"), table_name)
    count = service.import_single_csv(table_name=table_name, content=file.file.read())
    if count == 0:
        return ApiResponse(success=True, data={"count": 0}, message="CSV 檔案無資料列")
    return ApiResponse(success=True, data={"count": count}, message=f"已匯入 {count} 筆資料至 {table_name}")


@router.get("/export/{table_name}", summary="匯出 CSV")
def export_csv(
    table_name: str,
    user=Depends(require_role("admin")),
    service: AdminImportService = Depends(get_admin_import_service),
):
    validate_table(table_name)
    logger.warning("Admin user_id=%s 匯出 CSV: %s", user.get("sub"), table_name)
    path = service.export_table_to_csv(
        table_name=table_name, export_dir=Path("data/export"),
    )
    safe_filename = re.sub(r'[^A-Za-z0-9_\-]', '', table_name) + ".csv"
    return FileResponse(path=str(path), filename=safe_filename, media_type="text/csv")


@router.post("/reset", summary="清空資料庫", response_model=ApiResponse)
def reset_database(
    confirm: bool = Query(...),
    user=Depends(require_role("admin")),
    service: AdminImportService = Depends(get_admin_import_service),
):
    if not confirm:
        raise DomainException("請傳入 confirm=true 以確認清空資料庫")
    logger.warning("Admin user_id=%s 執行清空資料庫", user.get("sub"))
    deleted = service.reset_database(admin_user_id=int(user["sub"]))
    total = sum(deleted.values())
    return ApiResponse(success=True, data=deleted, message=f"已刪除 {total} 筆資料，Admin 帳號已保留")


@router.get("/system-status", summary="系統狀態", response_model=ApiResponse)
def system_status(
    user=Depends(require_role("admin")),
    repo: TableAdminRepository = Depends(get_admin_repo),
):
    return ApiResponse(
        success=True,
        data={
            "table_counts": repo.count_all(ALLOWED_TABLES),
            "role_counts": repo.role_counts(),
            "match_statuses": repo.match_status_counts(),
        },
        message="系統狀態查詢完成",
    )


@router.post("/export-all", summary="一鍵匯出全部")
def export_all(
    user=Depends(require_role("admin")),
    service: AdminImportService = Depends(get_admin_import_service),
):
    logger.warning("Admin user_id=%s 執行一鍵匯出全部資料表", user.get("sub"))
    zip_path = service.export_all_tables_to_zip(export_dir=Path("data/export"))
    return FileResponse(path=str(zip_path), filename="all_tables.zip", media_type="application/zip")


@router.post("/import-all", summary="一鍵匯入全部", response_model=ApiResponse)
def import_all(
    file: UploadFile = File(...),
    clear_first: bool = Query(False),
    user=Depends(require_role("admin")),
    service: AdminImportService = Depends(get_admin_import_service),
):
    logger.warning("Admin user_id=%s 執行一鍵匯入 (clear_first=%s)", user.get("sub"), clear_first)
    outcome = service.import_zip(
        zip_bytes=file.file.read(),
        admin_user_id=int(user["sub"]),
        clear_first=clear_first,
    )
    imported = outcome["imported"]
    errors = outcome["errors"]
    total = sum(imported.values())
    data = {"imported": imported}
    if errors:
        data["errors"] = errors
    msg = f"已匯入 {total} 筆資料（{len(imported)} 張表）"
    if errors:
        msg += f"，{sum(len(v) for v in errors.values())} 筆失敗"
    return ApiResponse(success=True, data=data, message=msg)


@router.get("/tasks/{task_id}", summary="查詢背景任務", response_model=ApiResponse)
def get_task_status(task_id: str, user=Depends(require_role("admin"))):
    from app.worker import huey as huey_instance
    try:
        raw = huey_instance.storage.peek_data(task_id)
    except Exception:
        # Bug #14: do not swallow silently; log then degrade to "pending"
        # so the admin dashboard does not crash.
        logger.exception("Huey peek_data failed for task_id=%s", task_id)
        return ApiResponse(success=True, data={"task_id": task_id, "status": "pending"})
    if raw is huey_instance.EmptyData:
        return ApiResponse(success=True, data={"task_id": task_id, "status": "pending"})
    try:
        import json
        result = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        try:
            import pickle
            result = pickle.loads(raw)
        except (pickle.UnpicklingError, EOFError, AttributeError, ImportError) as e:
            logger.warning("Cannot deserialize task result task_id=%s: %s", task_id, e)
            result = None
    if isinstance(result, Exception):
        return ApiResponse(success=True, data={"task_id": task_id, "status": "failed", "error": str(result)})
    return ApiResponse(success=True, data={"task_id": task_id, "status": "completed", "result": result})


# MAX_UPLOAD_SIZE re-exported for callers that still reference it.
__all__ = ["router", "MAX_UPLOAD_SIZE"]
