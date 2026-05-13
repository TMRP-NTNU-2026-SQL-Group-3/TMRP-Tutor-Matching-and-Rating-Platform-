from fastapi import APIRouter, Depends, HTTPException

from app.identity.api.dependencies import get_current_user, is_admin, require_role
from app.middleware.rate_limit import check_and_record_bucket
from app.shared.api.schemas import ApiResponse
from app.shared.domain.exceptions import PermissionDeniedError, TooManyRequestsError
from app.teaching.api.dependencies import get_session_service
from app.teaching.api.schemas import SessionCreateBody, SessionUpdate
from app.teaching.application.session_service import SessionAppService
from app.teaching.domain.exceptions import SessionNotFoundError

# Spec §7.6: POST/GET /api/matches/{match_id}/sessions
match_sessions_router = APIRouter(prefix="/api/matches", tags=["sessions"])
# Remaining session-specific routes stay under /api/sessions
router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# B6: Path-based rate-limiting in the middleware can't distinguish "60 session
# logs for one match in a minute" from "60 across 60 different matches". This
# per-match+tutor bucket isolates each match's log independently of others.
_SESSION_CREATE_LIMIT = 10
_SESSION_CREATE_WINDOW = 60


@match_sessions_router.post("/{match_id}/sessions", status_code=201, summary="新增上課日誌", response_model=ApiResponse)
def create_session(
    match_id: int,
    body: SessionCreateBody,
    user=Depends(require_role("tutor")),
    service: SessionAppService = Depends(get_session_service),
):
    tutor_user_id = int(user["sub"])
    # Keyed on match+tutor so the bucket survives IP changes (mobile networks,
    # roaming) but still isolates different matches from each other.
    bucket = f"session:create|match={match_id}|tutor={tutor_user_id}"
    if not check_and_record_bucket(bucket, _SESSION_CREATE_LIMIT, _SESSION_CREATE_WINDOW):
        raise TooManyRequestsError("此配對的上課日誌新增頻率過高，請稍後再試")
    session_id = service.create(
        tutor_user_id=tutor_user_id,
        match_id=match_id,
        session_date=body.session_date,
        hours=body.hours,
        content_summary=body.content_summary,
        homework=body.homework,
        student_performance=body.student_performance,
        next_plan=body.next_plan,
        visible_to_parent=body.visible_to_parent,
    )
    return ApiResponse(success=True, data={"session_id": session_id}, message="上課日誌已新增")


@match_sessions_router.get("/{match_id}/sessions", summary="列出上課日誌", response_model=ApiResponse)
def list_sessions(
    match_id: int,
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
    try:
        result = service.update(
            session_id=session_id,
            tutor_user_id=int(user["sub"]),
            updates=updates,
        )
    except (SessionNotFoundError, PermissionDeniedError):
        # SEC-10: normalize ownership failure to 404 so sequential integer IDs
        # cannot be enumerated by comparing 403 vs 404 response codes.
        raise HTTPException(status_code=404, detail="找不到此上課日誌")
    return ApiResponse(success=True, data={"session_id": result["session_id"]}, message=result["message"])



@router.get("/{session_id}/edit-logs", summary="查看修改紀錄", response_model=ApiResponse)
def get_edit_logs(
    session_id: int,
    user=Depends(get_current_user),
    service: SessionAppService = Depends(get_session_service),
):
    try:
        logs = service.get_edit_logs(
            session_id=session_id,
            user_id=int(user["sub"]),
            is_admin=is_admin(user),
        )
    except (SessionNotFoundError, PermissionDeniedError):
        raise HTTPException(status_code=404, detail="找不到此上課日誌")
    return ApiResponse(success=True, data=logs)
