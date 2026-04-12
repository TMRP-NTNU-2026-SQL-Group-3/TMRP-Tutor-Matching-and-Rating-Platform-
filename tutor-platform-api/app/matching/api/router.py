from fastapi import APIRouter, Depends

from app.catalog.infrastructure.catalog_query_adapter import CatalogQueryAdapter
from app.identity.api.dependencies import get_current_user, get_db, is_admin, require_role
from app.matching.api.schemas import MatchCreate, MatchStatusUpdate
from app.matching.application.match_app_service import MatchAppService
from app.matching.infrastructure.postgres_match_repo import PostgresMatchRepository
from app.shared.api.schemas import ApiResponse

router = APIRouter(prefix="/api/matches", tags=["matches"])


def _build_service(conn) -> MatchAppService:
    return MatchAppService(
        match_repo=PostgresMatchRepository(conn),
        catalog=CatalogQueryAdapter(conn),
        conn=conn,
    )


@router.post("", summary="建立配對邀請", description="家長為指定學生向家教發送配對邀請。", response_model=ApiResponse)
def create_match(body: MatchCreate, user=Depends(require_role("parent")), conn=Depends(get_db)):
    service = _build_service(conn)
    match_id = service.create_match(
        user_id=int(user["sub"]),
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
def list_matches(user=Depends(get_current_user), conn=Depends(get_db)):
    service = _build_service(conn)
    matches = service.list_matches(user_id=int(user["sub"]), role=user["role"])
    return ApiResponse(success=True, data=matches)


@router.get("/{match_id}", summary="取得配對詳情", response_model=ApiResponse)
def get_match_detail(match_id: int, user=Depends(get_current_user), conn=Depends(get_db)):
    service = _build_service(conn)
    data = service.get_detail(
        match_id=match_id,
        user_id=int(user["sub"]),
        is_admin=is_admin(user),
    )
    return ApiResponse(success=True, data=data)


@router.patch("/{match_id}/status", summary="更新配對狀態", response_model=ApiResponse)
def update_match_status(match_id: int, body: MatchStatusUpdate, user=Depends(get_current_user), conn=Depends(get_db)):
    service = _build_service(conn)
    result = service.update_status(
        match_id=match_id,
        action_str=body.action,
        reason=body.reason,
        user_id=int(user["sub"]),
        is_admin=is_admin(user),
    )
    from app.matching.domain.value_objects import MatchStatus
    status_label = MatchStatus(result["new_status"]).label
    return ApiResponse(
        success=True,
        data={"match_id": result["match_id"], "new_status": result["new_status"]},
        message=f"配對狀態已更新為「{status_label}」",
    )
