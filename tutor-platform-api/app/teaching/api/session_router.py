from fastapi import APIRouter, Depends, Query

from app.identity.api.dependencies import get_current_user, is_admin, require_role
from app.shared.api.schemas import ApiResponse
from app.teaching.api.dependencies import get_session_service
from app.teaching.api.schemas import SessionCreate, SessionUpdate
from app.teaching.application.session_service import SessionAppService

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", status_code=201, summary="新增上課日誌", response_model=ApiResponse)
def create_session(
    body: SessionCreate,
    user=Depends(require_role("tutor")),
    service: SessionAppService = Depends(get_session_service),
):
    session_id = service.create(
        tutor_user_id=int(user["sub"]),
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


@router.get("", summary="列出上課日誌", response_model=ApiResponse)
def list_sessions(
    match_id: int = Query(...),
    user=Depends(get_current_user),
    service: SessionAppService = Depends(get_session_service),
):
    sessions = service.list_for_match(
        match_id=match_id,
        user_id=int(user["sub"]),
        is_admin=is_admin(user),
    )
    return ApiResponse(success=True, data=sessions)


@router.put("/{session_id}", summary="修改上課日誌", response_model=ApiResponse)
def update_session(
    session_id: int,
    body: SessionUpdate,
    user=Depends(require_role("tutor")),
    service: SessionAppService = Depends(get_session_service),
):
    updates = body.model_dump(exclude_unset=True)
    result = service.update(
        session_id=session_id,
        tutor_user_id=int(user["sub"]),
        updates=updates,
    )
    return ApiResponse(success=True, data={"session_id": result["session_id"]}, message=result["message"])


@router.delete("/{session_id}", summary="刪除上課日誌", response_model=ApiResponse)
def delete_session(
    session_id: int,
    user=Depends(require_role("tutor")),
    service: SessionAppService = Depends(get_session_service),
):
    service.delete(
        session_id=session_id,
        tutor_user_id=int(user["sub"]),
    )
    return ApiResponse(success=True, message="上課日誌已刪除")


@router.get("/{session_id}/edit-logs", summary="查看修改紀錄", response_model=ApiResponse)
def get_edit_logs(
    session_id: int,
    user=Depends(get_current_user),
    service: SessionAppService = Depends(get_session_service),
):
    logs = service.get_edit_logs(
        session_id=session_id,
        user_id=int(user["sub"]),
        is_admin=is_admin(user),
    )
    return ApiResponse(success=True, data=logs)
