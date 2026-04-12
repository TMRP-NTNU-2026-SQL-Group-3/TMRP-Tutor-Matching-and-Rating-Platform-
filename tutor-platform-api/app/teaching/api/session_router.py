from fastapi import APIRouter, Depends, Query

from app.identity.api.dependencies import get_current_user, get_db, is_admin, require_role
from app.shared.api.schemas import ApiResponse
from app.shared.domain.exceptions import DomainException, NotFoundError, PermissionDeniedError
from app.shared.infrastructure.database_tx import transaction
from app.teaching.api.schemas import SessionCreate, SessionUpdate
from app.teaching.infrastructure.postgres_session_repo import PostgresSessionRepository

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", summary="新增上課日誌", response_model=ApiResponse)
def create_session(body: SessionCreate, user=Depends(require_role("tutor")), conn=Depends(get_db)):
    repo = PostgresSessionRepository(conn)
    user_id = int(user["sub"])
    match = repo.get_match_for_create(body.match_id)
    if not match:
        raise NotFoundError("找不到此配對")
    if match["tutor_user_id"] != user_id:
        raise PermissionDeniedError("只有此配對的老師可以新增上課日誌")
    if match["status"] not in ("active", "trial"):
        raise DomainException("只有進行中或試教中的配對可以記錄上課日誌")
    session_id = repo.create(
        match_id=body.match_id, session_date=body.session_date, hours=body.hours,
        content_summary=body.content_summary, homework=body.homework,
        student_performance=body.student_performance, next_plan=body.next_plan,
        visible_to_parent=body.visible_to_parent,
    )
    return ApiResponse(success=True, data={"session_id": session_id}, message="上課日誌已新增")


@router.get("", summary="列出上課日誌", response_model=ApiResponse)
def list_sessions(match_id: int = Query(...), user=Depends(get_current_user), conn=Depends(get_db)):
    repo = PostgresSessionRepository(conn)
    user_id = int(user["sub"])
    match = repo.get_match_participants(match_id)
    if not match:
        raise NotFoundError("找不到此配對")
    is_tutor = match["tutor_user_id"] == user_id
    is_parent = match["parent_user_id"] == user_id
    if not is_tutor and not is_parent and not is_admin(user):
        raise PermissionDeniedError("無權查看此配對的上課日誌")
    sessions = repo.list_by_match(match_id, parent_only=is_parent and not is_tutor)
    return ApiResponse(success=True, data=sessions)


@router.put("/{session_id}", summary="修改上課日誌", response_model=ApiResponse)
def update_session(session_id: int, body: SessionUpdate, user=Depends(require_role("tutor")), conn=Depends(get_db)):
    repo = PostgresSessionRepository(conn)
    user_id = int(user["sub"])
    session = repo.get_by_id(session_id)
    if not session:
        raise NotFoundError("找不到此上課日誌")
    match = repo.get_match_for_create(session["match_id"])
    if not match or match["tutor_user_id"] != user_id:
        raise PermissionDeniedError("只有此配對的老師可以修改上課日誌")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise DomainException("未提供任何修改欄位")
    if "visible_to_parent" in updates:
        if updates["visible_to_parent"] is None:
            del updates["visible_to_parent"]
        else:
            updates["visible_to_parent"] = bool(updates["visible_to_parent"])
    if not updates:
        return ApiResponse(success=True, data={"session_id": session_id}, message="無需更新的欄位")

    repo.validate_columns(list(updates.keys()), PostgresSessionRepository.ALLOWED_COLUMNS)
    with transaction(conn):
        session_fresh = repo.fetch_one("SELECT * FROM sessions WHERE session_id = %s", (session_id,))
        if not session_fresh:
            raise NotFoundError("找不到此上課日誌")
        diffs = []
        for field, new_val in updates.items():
            old_val = session_fresh.get(field)
            if field == "visible_to_parent":
                old_val = bool(old_val)
            old_str = str(old_val) if old_val is not None else ""
            new_str = str(new_val) if new_val is not None else ""
            if old_str != new_str:
                diffs.append((field, old_val, new_val))
        if not diffs:
            return ApiResponse(success=True, data={"session_id": session_id}, message="無實際變動")
        set_clause = ", ".join(f"{col} = %s" for col in updates)
        # 透過 repo.execute() 而非直接呼叫 cursor.execute()：
        # repo.execute() 已感知 transaction() 上下文，不會在交易中錯誤地 commit。
        repo.execute(
            f"UPDATE sessions SET {set_clause}, updated_at = NOW() WHERE session_id = %s",
            tuple(list(updates.values()) + [session_id]),
        )
        for field, old_val, new_val in diffs:
            repo.execute(
                "INSERT INTO session_edit_logs (session_id, field_name, old_value, new_value, edited_at) VALUES (%s, %s, %s, %s, NOW())",
                (session_id, field, str(old_val) if old_val is not None else None, str(new_val) if new_val is not None else None),
            )
    return ApiResponse(success=True, data={"session_id": session_id}, message="上課日誌已更新")


@router.get("/{session_id}/edit-logs", summary="查看修改紀錄", response_model=ApiResponse)
def get_edit_logs(session_id: int, user=Depends(get_current_user), conn=Depends(get_db)):
    repo = PostgresSessionRepository(conn)
    user_id = int(user["sub"])
    session = repo.get_by_id(session_id)
    if not session:
        raise NotFoundError("找不到此上課日誌")
    match = repo.get_match_participants(session["match_id"])
    if not match:
        raise NotFoundError("找不到此配對")
    is_tutor = match["tutor_user_id"] == user_id
    is_parent = match["parent_user_id"] == user_id
    if not is_tutor and not is_parent and not is_admin(user):
        raise PermissionDeniedError("無權查看此日誌的修改歷史")
    logs = repo.get_edit_logs(session_id)
    return ApiResponse(success=True, data=logs)
