from fastapi import APIRouter, Depends, Query

from app.database_tx import transaction
from app.dependencies import get_current_user, get_db, is_admin, require_role
from app.exceptions import AppException, ForbiddenException, NotFoundException
from app.models.common import ApiResponse
from app.models.session import SessionCreate, SessionUpdate
from app.repositories.session_repo import SessionRepository

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", summary="新增上課日誌", description="老師為進行中或試教中的配對新增上課紀錄。記錄教學日期、時數、內容摘要、作業、學生表現等。", response_model=ApiResponse)
def create_session(
    body: SessionCreate,
    user=Depends(require_role("tutor")),
    conn=Depends(get_db),
):
    repo = SessionRepository(conn)
    user_id = int(user["sub"])

    match = repo.get_match_for_create(body.match_id)
    if not match:
        raise NotFoundException("找不到此配對")
    if match["tutor_user_id"] != user_id:
        raise ForbiddenException("只有此配對的老師可以新增上課日誌")
    if match["status"] not in ("active", "trial"):
        raise AppException("只有進行中或試教中的配對可以記錄上課日誌")

    session_id = repo.create(
        match_id=body.match_id,
        session_date=body.session_date,
        hours=body.hours,
        content_summary=body.content_summary,
        homework=body.homework,
        student_performance=body.student_performance,
        next_plan=body.next_plan,
        visible_to_parent=body.visible_to_parent,
    )
    return ApiResponse(success=True, data={"session_id": session_id}, message="上課日誌已新增")


@router.get("", summary="列出上課日誌", description="列出指定配對的所有上課日誌。家長僅能看到 visible_to_parent 為 true 的紀錄。", response_model=ApiResponse)
def list_sessions(
    match_id: int = Query(...),
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    repo = SessionRepository(conn)
    user_id = int(user["sub"])

    match = repo.get_match_participants(match_id)
    if not match:
        raise NotFoundException("找不到此配對")

    is_tutor = match["tutor_user_id"] == user_id
    is_parent = match["parent_user_id"] == user_id

    if not is_tutor and not is_parent and not is_admin(user):
        raise ForbiddenException("無權查看此配對的上課日誌")

    sessions = repo.list_by_match(match_id, parent_only=is_parent and not is_tutor)
    return ApiResponse(success=True, data=sessions)


@router.put("/{session_id}", summary="修改上課日誌", description="修改上課日誌的內容，系統會自動記錄每個欄位的修改前後差異至 Session_Edit_Logs。", response_model=ApiResponse)
def update_session(
    session_id: int,
    body: SessionUpdate,
    user=Depends(require_role("tutor")),
    conn=Depends(get_db),
):
    repo = SessionRepository(conn)
    user_id = int(user["sub"])

    session = repo.get_by_id(session_id)
    if not session:
        raise NotFoundException("找不到此上課日誌")

    match = repo.get_match_for_create(session["match_id"])
    if not match or match["tutor_user_id"] != user_id:
        raise ForbiddenException("只有此配對的老師可以修改上課日誌")

    # 收集有變動的欄位（exclude_unset 允許前端送 null 清空欄位）
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise AppException("未提供任何修改欄位")

    # 處理 visible_to_parent 轉換（boolean 欄位不接受 null，送 null 視為不更新）
    if "visible_to_parent" in updates:
        if updates["visible_to_parent"] is None:
            del updates["visible_to_parent"]
        else:
            updates["visible_to_parent"] = bool(updates["visible_to_parent"])

    if not updates:
        return ApiResponse(success=True, data={"session_id": session_id}, message="無需更新的欄位")

    # 在交易中重新讀取最新資料，確保讀取-比對-更新的原子性
    repo.validate_columns(list(updates.keys()), SessionRepository.ALLOWED_COLUMNS)
    with transaction(conn):
        # 在交易內重新取得 session，避免並發更新時讀到過時的舊值
        session_fresh = repo.fetch_one(
            "SELECT * FROM sessions WHERE session_id = %s", (session_id,)
        )
        if not session_fresh:
            raise NotFoundException("找不到此上課日誌")

        # 以交易內的最新值重新計算差異
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
        repo.cursor.execute(
            f"UPDATE sessions SET {set_clause}, updated_at = NOW() WHERE session_id = %s",
            list(updates.values()) + [session_id],
        )
        for field, old_val, new_val in diffs:
            repo.cursor.execute(
                "INSERT INTO session_edit_logs (session_id, field_name, old_value, new_value, edited_at) "
                "VALUES (%s, %s, %s, %s, NOW())",
                (session_id, field,
                 str(old_val) if old_val is not None else None,
                 str(new_val) if new_val is not None else None),
            )

    return ApiResponse(success=True, data={"session_id": session_id}, message="上課日誌已更新")


@router.get("/{session_id}/edit-logs", summary="查看修改紀錄", description="查看指定上課日誌的所有修改歷史，包含欄位名稱、修改前後的值、修改時間。", response_model=ApiResponse)
def get_edit_logs(
    session_id: int,
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    repo = SessionRepository(conn)
    user_id = int(user["sub"])

    session = repo.get_by_id(session_id)
    if not session:
        raise NotFoundException("找不到此上課日誌")

    match = repo.get_match_participants(session["match_id"])
    if not match:
        raise NotFoundException("找不到此配對")

    is_tutor = match["tutor_user_id"] == user_id
    is_parent = match["parent_user_id"] == user_id
    if not is_tutor and not is_parent and not is_admin(user):
        raise ForbiddenException("無權查看此日誌的修改歷史")

    logs = repo.get_edit_logs(session_id)
    return ApiResponse(success=True, data=logs)
