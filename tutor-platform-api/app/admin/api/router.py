import logging
import re
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from app.admin.api.dependencies import get_admin_import_service, get_admin_repo
from app.admin.application.import_service import AdminImportService, MAX_UPLOAD_SIZE
from app.admin.domain.tables import (
    ALLOWED_TABLES,
    EXPORTABLE_TABLES,
    DELETE_ORDER,
    validate_exportable_table,
    validate_table,
)
from app.admin.infrastructure.table_admin_repo import TableAdminRepository
from app.identity.api.dependencies import get_db, require_role
from app.shared.infrastructure.database_tx import transaction
from app.middleware.rate_limit import check_and_record_bucket
from app.shared.api.schemas import ApiResponse
from app.shared.infrastructure.security import (
    consume_reset_confirmation_jti,
    create_reset_confirmation_token,
    decode_reset_confirmation_token,
    hash_password,
    revoke_all_user_tokens,
    verify_password,
)

logger = logging.getLogger("app.admin")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_EXPORT_DIR = _PROJECT_ROOT / "data" / "export"
_BACKUP_DIR = _PROJECT_ROOT / "data" / "backups"

router = APIRouter(prefix="/api/admin", tags=["admin"])


class _AdminPasswordResetBody(BaseModel):
    new_password: str = Field(..., min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if len(v) < 10:
            raise ValueError("密碼長度至少 10 個字元")
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("密碼須同時包含英文字母與數字")
        return v


# SEC-3: per-user rate limit on the destructive reset-confirm step.
# Distinct from the per-IP cap in RateLimitMiddleware — a single compromised
# admin account should not be able to wipe the database more than once per week
# regardless of how many IPs the attacker rotates through.
_ADMIN_RESET_CONFIRM_USER_WINDOW = 604800  # 7 days

# SEC-11: fixed advisory lock key that serializes concurrent DB-reset flows.
# pg_try_advisory_xact_lock is transaction-scoped; the lock is held for the
# lifetime of the transaction(conn) block that wraps the reset sequence.
_DB_RESET_LOCK_KEY = 7_329_847_234


@router.get("/tables", summary="可操作的資料表清單", response_model=ApiResponse)
def list_tables(user=Depends(require_role("admin"))):
    # Surface the server-authoritative table allow/deny lists so the SPA can
    # disable export controls for tables in EXPORT_DENYLIST (e.g. `users`,
    # which contains password_hash) instead of letting the click round-trip
    # to a 4xx. The DELETE_ORDER tuple preserves the dependency-aware order
    # used by import/export so the dropdowns render in a stable, meaningful
    # sequence rather than the unordered set form.
    exportable = [t for t in DELETE_ORDER if t in EXPORTABLE_TABLES]
    return ApiResponse(
        success=True,
        data={"allowed": list(DELETE_ORDER), "exportable": exportable},
    )


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
    # B8: run_seed no longer commits internally. Own the transaction here so
    # a mid-run failure rolls everything back instead of leaving partial rows.
    with transaction(repo.conn):
        result = run_seed(repo.conn)
    if result.get("skipped"):
        return ApiResponse(success=True, data=result, message=result.get("message", "已跳過"))
    total = sum(v for v in result.values() if isinstance(v, int))
    return ApiResponse(success=True, data=result, message=f"已產生 {total} 筆假資料")


@router.post("/import/{table_name}", summary="匯入 CSV", response_model=ApiResponse)
def import_csv(
    table_name: str,
    file: UploadFile = File(...),
    user=Depends(require_role("admin")),
    service: AdminImportService = Depends(get_admin_import_service),
):
    validate_table(table_name)
    # SEC-10: validate Content-Type before reading the body to fail fast.
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ("text/csv", "application/csv", "text/plain"):
        raise HTTPException(
            status_code=415,
            detail="僅接受 CSV 格式（Content-Type: text/csv）",
        )
    logger.warning("Admin user_id=%s 匯入 CSV 至 %s", user.get("sub"), table_name)
    # LOW-3: enforce the same size cap as import_zip so a compromised or
    # careless admin cannot OOM the worker via a huge single-CSV upload.
    data = file.file.read(MAX_UPLOAD_SIZE + 1)
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"上傳檔案過大（上限 {MAX_UPLOAD_SIZE // 1024 // 1024} MB）",
        )
    count = service.import_single_csv(table_name=table_name, content=data)
    if count == 0:
        return ApiResponse(success=True, data={"count": 0}, message="CSV 檔案無資料列")
    return ApiResponse(success=True, data={"count": count}, message=f"已匯入 {count} 筆資料至 {table_name}")


@router.post(
    "/export/{table_name}",
    summary="匯出 CSV",
    response_class=FileResponse,
    responses={200: {"content": {"text/csv": {}}, "description": "CSV 檔案"}},
)
def export_csv(
    table_name: str,
    user=Depends(require_role("admin")),
    service: AdminImportService = Depends(get_admin_import_service),
):
    validate_exportable_table(table_name)
    logger.warning("Admin user_id=%s 匯出 CSV: %s", user.get("sub"), table_name)
    path = service.export_table_to_csv(
        table_name=table_name, export_dir=_EXPORT_DIR,
    )
    safe_filename = re.sub(r'[^A-Za-z0-9_\-]', '', table_name) + ".csv"
    return FileResponse(path=str(path), filename=safe_filename, media_type="text/csv")


# H-04: destructive DB wipe is gated by a two-step flow.
#
#   Step 1  POST /api/admin/reset/request  →  issue a short-lived reset token
#                                             bound to the caller's user_id
#   Step 2  POST /api/admin/reset/confirm  →  require the reset token + the
#                                             admin's plaintext password,
#                                             auto-export a backup ZIP, then
#                                             perform the reset.
#
# This turns a single stolen access token into an insufficient credential for
# the nuclear "wipe everything" operation, and the auto-backup provides a
# recovery path even if a legitimate admin makes a mistake.

@router.post("/reset", summary="請求清空資料庫 (Step 1 of 2)", response_model=ApiResponse)
@router.post("/reset/request", summary="請求清空資料庫 (Step 1 of 2)", response_model=ApiResponse, include_in_schema=False)
def request_reset(request: Request, user=Depends(require_role("admin"))):
    token = create_reset_confirmation_token(user_id=int(user["sub"]))
    logger.warning(
        "Admin reset requested by user_id=%s ip=%s jti=%s",
        user.get("sub"),
        request.client.host if request.client else "unknown",
        user.get("jti"),
    )
    return ApiResponse(
        success=True,
        data={"reset_token": token, "expires_in": 300},
        message="請於 5 分鐘內以密碼確認此操作",
    )


@router.post("/reset/confirm", summary="確認清空資料庫 (Step 2 of 2)", response_model=ApiResponse)
def confirm_reset(
    request: Request,
    reset_token: str = Body(..., embed=True),
    password: str = Body(..., embed=True),
    user=Depends(require_role("admin")),
    service: AdminImportService = Depends(get_admin_import_service),
    conn=Depends(get_db),
):
    # SEC-3: per-user rate limit — independent of the per-IP cap. A single
    # admin account (or a compromised one) cannot execute more than one DB wipe
    # per 7-day window regardless of IP rotation.
    user_reset_bucket = f"admin_reset_confirm_user|{user['sub']}"
    if not check_and_record_bucket(
        user_reset_bucket,
        1,
        _ADMIN_RESET_CONFIRM_USER_WINDOW,
        fail_closed=True,
    ):
        logger.warning(
            "Admin reset confirm: per-user rate limit hit user_id=%s ip=%s",
            user.get("sub"),
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(status_code=429, detail="此帳號近期已執行過重設操作，請 7 天後再試")

    # SEC-11: serialize concurrent reset flows. pg_try_advisory_xact_lock is
    # transaction-scoped; wrapping everything in transaction(conn) guarantees
    # the lock is held through reset_database() completion and cannot be
    # released early by an accidental auto-commit on conn.
    with transaction(conn):
        with conn.cursor() as _lk_cur:
            _lk_cur.execute("SELECT pg_try_advisory_xact_lock(%s::bigint)", (_DB_RESET_LOCK_KEY,))
            _lock_acquired = _lk_cur.fetchone()[0]
        if not _lock_acquired:
            logger.warning(
                "Admin reset confirm: concurrent lock blocked user_id=%s ip=%s",
                user.get("sub"),
                request.client.host if request.client else "unknown",
            )
            raise HTTPException(status_code=409, detail="另一個重設操作正在進行中，請稍後再試")

        payload = decode_reset_confirmation_token(reset_token)
        if not payload or payload.get("sub") != str(user["sub"]):
            logger.warning(
                "Admin reset confirm: invalid/mismatched reset token user_id=%s ip=%s",
                user.get("sub"),
                request.client.host if request.client else "unknown",
            )
            raise HTTPException(status_code=401, detail="Reset token 無效或已過期")

        # LOW-4: burn the reset JTI up-front so neither a successful nor a failed
        # attempt leaves the token replayable within its 5-minute TTL. If the
        # insert finds an existing row, this token has already been used.
        reset_jti = payload.get("jti")
        if not reset_jti or not consume_reset_confirmation_jti(reset_jti):
            logger.warning(
                "Admin reset confirm: reset token replay rejected user_id=%s ip=%s jti=%s",
                user.get("sub"),
                request.client.host if request.client else "unknown",
                reset_jti,
            )
            raise HTTPException(status_code=401, detail="Reset token 已使用或無效")

        with conn.cursor() as cur:
            cur.execute(
                "SELECT password_hash FROM users WHERE user_id = %s FOR UPDATE",
                (int(user["sub"]),),
            )
            row = cur.fetchone()
        if not row or not verify_password(password, row[0]):
            logger.warning(
                "Admin reset confirm: password re-verification FAILED user_id=%s ip=%s",
                user.get("sub"),
                request.client.host if request.client else "unknown",
            )
            raise HTTPException(status_code=401, detail="密碼驗證失敗")

        backup_dir = _BACKUP_DIR
        try:
            backup_path = service.export_all_tables_to_zip(
                export_dir=backup_dir,
                zip_name=f"pre-reset-{payload['jti']}.zip",
                # DR artefact written to a server-local path — include users so a
                # mistaken reset is actually recoverable from this backup.
                include_sensitive=True,
            )
        except Exception:
            # An empty DB has nothing to export; fall through without a backup
            # rather than blocking a legitimate reset. Still log so the audit
            # trail shows the attempt.
            logger.warning("Pre-reset backup skipped (export failed)")
            backup_path = None

        logger.warning(
            "Admin reset CONFIRMED user_id=%s ip=%s jti=%s backup=%s",
            user.get("sub"),
            request.client.host if request.client else "unknown",
            user.get("jti"),
            backup_path is not None,
        )
        deleted = service.reset_database(admin_user_id=int(user["sub"]))
        total = sum(deleted.values())
    # Return only a boolean: the backup path lives on the server filesystem
    # and its filename embeds the reset JTI. Surfacing it invites a caller
    # to infer paths and gives an attacker with stolen admin creds a
    # predictable artefact name to target. The log above records only whether
    # a backup was created (True/False), not the path.
    return ApiResponse(
        success=True,
        data={"deleted": deleted, "backup_created": backup_path is not None},
        message=f"已刪除 {total} 筆資料，Admin 帳號已保留",
    )


# GDPR: users cannot be hard-deleted because matches.terminated_by,
# matches.parent_user_id, reviews.reviewer_user_id and exams.added_by_user_id
# all use ON DELETE RESTRICT to keep the audit trail intact. This endpoint
# gives admins the compliant alternative — replace the PII, invalidate the
# credential, keep the user_id so FKs stay resolvable. The row is NOT
# removed.
@router.post("/users/{user_id}/anonymize", summary="匿名化使用者", response_model=ApiResponse)
def anonymize_user(
    user_id: int,
    user=Depends(require_role("admin")),
    repo: TableAdminRepository = Depends(get_admin_repo),
):
    # Self-anonymization would orphan the platform — block it up-front so a
    # slip of the finger can't lock every operator out.
    if int(user["sub"]) == user_id:
        raise HTTPException(status_code=400, detail="無法匿名化自己的帳號")
    # Block anonymizing the only remaining admin to preserve break-glass access.
    target_role = repo.get_user_role(user_id)
    if target_role is None:
        raise HTTPException(status_code=404, detail="使用者不存在")
    # I-03: if the target is admin, make sure it's not the last one standing.
    # count_admins() excludes already-anonymized rows so repeated anonymization
    # attempts cannot whittle the roster down to zero.
    if target_role == "admin" and repo.count_admins() <= 1:
        raise HTTPException(
            status_code=400,
            detail="無法匿名化系統中最後一位管理員",
        )
    logger.warning(
        "Admin user_id=%s anonymizing user_id=%s (role=%s)",
        user.get("sub"), user_id, target_role,
    )
    with transaction(repo.conn):
        try:
            updated = repo.anonymize_user(user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="該使用者仍有進行中的配對，請先結束後再進行匿名化")
        if not updated:
            raise HTTPException(status_code=404, detail="使用者不存在")
        repo.record_admin_action(
            actor_user_id=int(user["sub"]),
            action="anonymize_user",
            resource_id=user_id,
            old_value=target_role,
        )
    return ApiResponse(
        success=True,
        data={"user_id": user_id},
        message="使用者已匿名化（保留 user_id 以維護審計關聯）",
    )


@router.post("/users/{user_id}/reset-password", summary="重設使用者密碼", response_model=ApiResponse)
def admin_reset_user_password(
    request: Request,
    user_id: int,
    body: _AdminPasswordResetBody,
    user=Depends(require_role("admin")),
    repo: TableAdminRepository = Depends(get_admin_repo),
):
    with transaction(repo.conn):
        found = repo.reset_user_password(user_id, hash_password(body.new_password))
        if not found:
            raise HTTPException(status_code=404, detail="使用者不存在")
        # SEC-2: revoke all refresh tokens for the target user so they cannot
        # silently obtain new access tokens after an admin-forced password reset.
        revoke_all_user_tokens(user_id, conn=repo.conn)
        repo.record_admin_action(
            actor_user_id=int(user["sub"]),
            action="admin_reset_password",
            resource_id=user_id,
        )
    # SEC-05: also emit to application log for real-time alerting.
    logger.warning(
        "Admin user_id=%s reset password for user_id=%s ip=%s",
        user.get("sub"), user_id,
        request.client.host if request.client else "unknown",
    )
    return ApiResponse(success=True, data={"user_id": user_id}, message="使用者密碼已重設")


@router.get("/system-status", summary="系統狀態", response_model=ApiResponse)
def system_status(
    user=Depends(require_role("admin")),
    repo: TableAdminRepository = Depends(get_admin_repo),
):
    # I-13: surface pool utilisation alongside the other operator metrics
    # so saturation is visible before requests start failing.
    from app.shared.infrastructure.database import pool_stats
    try:
        db_pool = pool_stats()
    except Exception:
        logger.exception("pool_stats failed")
        db_pool = {"error": "pool stats unavailable"}
    return ApiResponse(
        success=True,
        data={
            "table_counts": repo.count_all(ALLOWED_TABLES),
            "role_counts": repo.role_counts(),
            "match_statuses": repo.match_status_counts(),
            "db_pool": db_pool,
        },
        message="系統狀態查詢完成",
    )


@router.post(
    "/export-all",
    summary="一鍵匯出全部",
    response_class=FileResponse,
    responses={200: {"content": {"application/zip": {}}, "description": "ZIP 壓縮檔"}},
)
def export_all(
    user=Depends(require_role("admin")),
    service: AdminImportService = Depends(get_admin_import_service),
):
    logger.warning("Admin user_id=%s 執行一鍵匯出全部資料表", user.get("sub"))
    zip_path = service.export_all_tables_to_zip(export_dir=_EXPORT_DIR)
    return FileResponse(path=str(zip_path), filename="all_tables.zip", media_type="application/zip")


@router.post("/import-all", summary="一鍵匯入全部", response_model=ApiResponse)
def import_all(
    file: UploadFile = File(...),
    clear_first: bool = Query(False),
    user=Depends(require_role("admin")),
    service: AdminImportService = Depends(get_admin_import_service),
):
    # SEC-21: validate Content-Type before reading the body, consistent with import_csv.
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ("application/zip", "application/x-zip-compressed", "application/octet-stream"):
        raise HTTPException(
            status_code=415,
            detail="僅接受 ZIP 格式（Content-Type: application/zip）",
        )
    logger.warning("Admin user_id=%s 執行一鍵匯入 (clear_first=%s)", user.get("sub"), clear_first)
    zip_bytes = file.file.read(MAX_UPLOAD_SIZE + 1)
    if len(zip_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"上傳檔案過大（上限 {MAX_UPLOAD_SIZE // 1024 // 1024} MB）",
        )
    outcome = service.import_zip(
        zip_bytes=zip_bytes,
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
    import json
    from app.worker import huey as huey_instance
    try:
        raw = huey_instance.storage.peek_data(task_id)
    except Exception:
        # Bug #14: do not swallow silently; log then degrade to "pending"
        # so the admin dashboard does not crash.
        logger.exception("Huey peek_data failed for task_id=%s", task_id)
        return ApiResponse(success=True, data={"task_id": task_id, "status": "pending", "error": True})
    if raw is huey_instance.EmptyData:
        return ApiResponse(success=True, data={"task_id": task_id, "status": "pending"})
    # H-02: task payloads are JSON (see app.shared.infrastructure.huey_json_serializer).
    # Refuse to fall back to pickle — deserializing untrusted storage bytes as
    # pickle is a remote-code-execution primitive (CWE-502).
    try:
        result = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        # I-11: corrupted payloads were previously returned with a generic
        # "not valid JSON" message, leaving the admin with no next step.
        # Surface (a) the decode error class so triage knows if this is a
        # malformed UTF-8 vs structural JSON issue, and (b) an explicit
        # recovery hint — the task row should be purged from huey.db so
        # /tasks/{id} stops wedging on the same corrupt entry forever.
        logger.error("Non-JSON task payload task_id=%s: %s", task_id, e)
        return ApiResponse(
            success=False,
            data={
                "task_id": task_id,
                "status": "corrupted",
                "error_type": type(e).__name__,
                "hint": (
                    "Task result payload is unreadable. Check the huey worker log "
                    "for the originating task, then delete the row from the Huey "
                    "SQLite store (huey_db_path) so subsequent polls recover."
                ),
            },
            message="Task result is not valid JSON",
        )
    if isinstance(result, dict) and result.get("__huey_error__"):
        meta = result.get("metadata") or {}
        return ApiResponse(
            success=True,
            data={"task_id": task_id, "status": "failed", "error": meta.get("error", "unknown error")},
        )
    if isinstance(result, dict) and result.get("__exception__"):
        return ApiResponse(
            success=True,
            data={"task_id": task_id, "status": "failed", "error": result.get("message", "")},
        )
    return ApiResponse(success=True, data={"task_id": task_id, "status": "completed", "result": result})


# MAX_UPLOAD_SIZE re-exported for callers that still reference it.
__all__ = ["router", "MAX_UPLOAD_SIZE"]
