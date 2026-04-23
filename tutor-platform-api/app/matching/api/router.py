from fastapi import APIRouter, Depends, Query

from app.identity.api.dependencies import get_current_user, is_admin, require_role
from app.matching.api.dependencies import get_match_service
from app.matching.api.schemas import MatchCreate, MatchDetailResponse, MatchStatusUpdate
from app.matching.application.match_app_service import MatchAppService
from app.matching.domain.value_objects import MatchStatus
from app.middleware.rate_limit import check_and_record_bucket
from app.shared.api.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.shared.api.schemas import ApiResponse
from app.shared.domain.exceptions import TooManyRequestsError

router = APIRouter(prefix="/api/matches", tags=["matches"])

# Mirror of exam_router's per-student bucket (B6). Even under the global
# /api/matches path limit, a single parent could flood one tutor's inbox
# with invitations; cap invitations per (tutor, parent) pair.
_MATCH_CREATE_LIMIT = 10
_MATCH_CREATE_WINDOW = 3600


@router.post("", summary="建立配對邀請", description="家長為指定學生向家教發送配對邀請。", response_model=ApiResponse)
def create_match(
    body: MatchCreate,
    user=Depends(require_role("parent")),
    service: MatchAppService = Depends(get_match_service),
):
    user_id = int(user["sub"])
    bucket = f"match:create|tutor={body.tutor_id}|user={user_id}"
    if not check_and_record_bucket(bucket, _MATCH_CREATE_LIMIT, _MATCH_CREATE_WINDOW):
        raise TooManyRequestsError("對此家教的邀請頻率過高，請稍後再試")
    match_id = service.create_match(
        user_id=user_id,
        tutor_id=body.tutor_id,
        student_id=body.student_id,
        subject_id=body.subject_id,
        hourly_rate=body.hourly_rate,
        sessions_per_week=body.sessions_per_week,
        want_trial=body.want_trial,
        invite_message=body.invite_message,
    )
    return ApiResponse(success=True, data={"match_id": match_id}, message="媒合邀請已送出")


@router.get("", summary="列出我的配對", response_model=ApiResponse)
def list_matches(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    user=Depends(get_current_user),
    service: MatchAppService = Depends(get_match_service),
):
    data = service.list_matches(
        user_id=int(user["sub"]), role=user["role"],
        page=page, page_size=page_size,
    )
    return ApiResponse(success=True, data=data)


@router.get("/{match_id}", summary="取得配對詳情", response_model=ApiResponse)
def get_match_detail(
    match_id: int,
    user=Depends(get_current_user),
    service: MatchAppService = Depends(get_match_service),
):
    view = service.get_detail(
        match_id=match_id,
        user_id=int(user["sub"]),
        is_admin=is_admin(user),
    )
    payload = MatchDetailResponse.from_entity(
        view.match, is_parent=view.is_parent, is_tutor=view.is_tutor,
    )
    return ApiResponse(success=True, data=payload.model_dump())


@router.patch("/{match_id}/status", summary="更新配對狀態", response_model=ApiResponse)
def update_match_status(
    match_id: int,
    body: MatchStatusUpdate,
    user=Depends(get_current_user),
    service: MatchAppService = Depends(get_match_service),
):
    result = service.update_status(
        match_id=match_id,
        action_str=body.action,
        reason=body.reason,
        user_id=int(user["sub"]),
        is_admin=is_admin(user),
        contract_terms={
            "hourly_rate": body.hourly_rate,
            "sessions_per_week": body.sessions_per_week,
            "start_date": body.start_date,
        },
    )
    status_label = MatchStatus(result["new_status"]).label
    return ApiResponse(
        success=True,
        data={"match_id": result["match_id"], "new_status": result["new_status"]},
        message=f"配對狀態已更新為「{status_label}」",
    )
