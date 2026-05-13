import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query

from app.analytics.api.dependencies import get_stats_service
from app.analytics.application.stats_service import StatsAppService
from app.identity.api.dependencies import get_current_user, is_admin, require_role
from app.shared.api.schemas import ApiResponse
from app.shared.domain.exceptions import DomainException

router = APIRouter(prefix="/api/stats", tags=["stats"])
logger = logging.getLogger("app.analytics")

_TZ_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*/[A-Za-z][A-Za-z0-9_/]*$")


def _validate_tz(tz: str) -> str:
    if not _TZ_RE.match(tz):
        raise DomainException("無效的時區格式")
    try:
        ZoneInfo(tz)
    except ZoneInfoNotFoundError:
        raise DomainException(f"不支援的時區：{tz}")
    return tz


def _parse_month(month: str | None, tz: str = "Asia/Taipei") -> tuple[int, int]:
    if month:
        year, mon = map(int, month.split("-"))
        if not (1 <= mon <= 12):
            raise DomainException("無效的月份值（1-12）")
        if not (2000 <= year <= 2100):
            raise DomainException("無效的年份值（2000-2100）")
    else:
        now = datetime.now(ZoneInfo(tz))
        year, mon = now.year, now.month
    return year, mon


@router.get("/income", summary="家教收入統計", response_model=ApiResponse)
def get_income_stats(
    month: str = Query(None, pattern=r"^\d{4}-\d{2}$"),
    tz: str = Query("Asia/Taipei"),
    user=Depends(require_role("tutor")),
):
    tz = _validate_tz(tz)
    _parse_month(month, tz)  # validate inputs before dispatch
    from app.tasks.stats_tasks import calculate_income_stats
    task = calculate_income_stats(int(user["sub"]), month)
    return ApiResponse(success=True, data={"task_id": str(task.id)}, message="統計任務已排入佇列")


@router.get("/expense", summary="家長支出統計", response_model=ApiResponse)
def get_expense_stats(
    month: str = Query(None, pattern=r"^\d{4}-\d{2}$"),
    tz: str = Query("Asia/Taipei"),
    user=Depends(require_role("parent")),
):
    tz = _validate_tz(tz)
    _parse_month(month, tz)  # validate inputs before dispatch
    from app.tasks.stats_tasks import calculate_expense_stats
    task = calculate_expense_stats(int(user["sub"]), month)
    return ApiResponse(success=True, data={"task_id": str(task.id)}, message="統計任務已排入佇列")


@router.get("/tasks/{task_id}", summary="查詢統計背景任務", response_model=ApiResponse)
def get_stats_task(task_id: str, user=Depends(get_current_user)):
    import json
    from app.worker import huey as huey_instance
    try:
        raw = huey_instance.storage.peek_data(task_id)
    except Exception:
        logger.exception("Huey peek_data failed for task_id=%s", task_id)
        return ApiResponse(success=True, data={"task_id": task_id, "status": "pending", "error": True})
    if raw is huey_instance.EmptyData:
        return ApiResponse(success=True, data={"task_id": task_id, "status": "pending"})
    try:
        result = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error("Non-JSON task payload task_id=%s: %s", task_id, e)
        return ApiResponse(
            success=False,
            data={"task_id": task_id, "status": "corrupted"},
            message="Task result is not valid JSON",
        )
    return ApiResponse(success=True, data={"task_id": task_id, "status": "complete", "result": result})


@router.get("/student-progress/{student_id}", summary="學生成績趨勢", response_model=ApiResponse)
def get_student_progress(
    student_id: int,
    subject_id: int | None = Query(None),
    user=Depends(get_current_user),
    service: StatsAppService = Depends(get_stats_service),
):
    # SEC-7: explicit route-level ownership gate — only parents (who must own
    # the student) and admins may query this endpoint. The service enforces the
    # parent-owns-student check; this guard makes the constraint visible at the
    # route boundary and blocks other roles before any service call is made.
    caller_is_admin = is_admin(user)
    if not caller_is_admin and user.get("role") != "parent":
        raise DomainException("僅家長或管理員可查詢學生成績趨勢", status_code=403)
    data = service.student_progress(
        student_id=student_id,
        user_id=int(user["sub"]),
        is_admin=caller_is_admin,
        subject_id=subject_id,
    )
    return ApiResponse(success=True, data=data)
