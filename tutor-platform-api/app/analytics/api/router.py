from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.analytics.api.dependencies import get_stats_service
from app.analytics.application.stats_service import StatsAppService
from app.identity.api.dependencies import get_current_user, is_admin, require_role
from app.shared.api.schemas import ApiResponse
from app.shared.domain.exceptions import DomainException

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _parse_month(month: str | None) -> tuple[int, int]:
    if month:
        year, mon = map(int, month.split("-"))
        if not (1 <= mon <= 12):
            raise DomainException("無效的月份值（1-12）")
        if not (2000 <= year <= 2100):
            raise DomainException("無效的年份值（2000-2100）")
    else:
        now = datetime.now()
        year, mon = now.year, now.month
    return year, mon


@router.get("/income", summary="家教收入統計", response_model=ApiResponse)
def get_income_stats(
    month: str = Query(None, pattern=r"^\d{4}-\d{2}$"),
    user=Depends(require_role("tutor")),
    service: StatsAppService = Depends(get_stats_service),
):
    year, mon = _parse_month(month)
    data = service.income_stats(user_id=int(user["sub"]), year=year, month=mon)
    return ApiResponse(success=True, data=data)


@router.get("/expense", summary="家長支出統計", response_model=ApiResponse)
def get_expense_stats(
    month: str = Query(None, pattern=r"^\d{4}-\d{2}$"),
    user=Depends(require_role("parent")),
    service: StatsAppService = Depends(get_stats_service),
):
    year, mon = _parse_month(month)
    data = service.expense_stats(parent_user_id=int(user["sub"]), year=year, month=mon)
    return ApiResponse(success=True, data=data)


@router.get("/student-progress/{student_id}", summary="學生成績趨勢", response_model=ApiResponse)
def get_student_progress(
    student_id: int,
    subject_id: int | None = Query(None),
    user=Depends(get_current_user),
    service: StatsAppService = Depends(get_stats_service),
):
    data = service.student_progress(
        student_id=student_id,
        user_id=int(user["sub"]),
        is_admin=is_admin(user),
        subject_id=subject_id,
    )
    return ApiResponse(success=True, data=data)
