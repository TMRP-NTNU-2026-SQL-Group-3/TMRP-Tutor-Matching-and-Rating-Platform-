from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.analytics.infrastructure.postgres_stats_repo import PostgresStatsRepository
from app.identity.api.dependencies import get_current_user, get_db, is_admin, require_role
from app.shared.api.schemas import ApiResponse
from app.shared.domain.exceptions import DomainException, NotFoundError, PermissionDeniedError

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
def get_income_stats(month: str = Query(None, pattern=r"^\d{4}-\d{2}$"), user=Depends(require_role("tutor")), conn=Depends(get_db)):
    repo = PostgresStatsRepository(conn)
    year, mon = _parse_month(month)
    tutor = repo.get_tutor_by_user(int(user["sub"]))
    if not tutor:
        return ApiResponse(success=True, data={"year": year, "month": mon, "total_hours": 0, "total_income": 0, "session_count": 0, "breakdown": []})
    tutor_id = tutor["tutor_id"]
    summary = repo.income_summary(tutor_id, year, mon)
    breakdown = repo.income_breakdown(tutor_id, year, mon)
    if summary is None:
        summary = {"total_hours": 0, "total_income": 0, "session_count": 0}
    for row in breakdown:
        row["hours"] = float(row["hours"] or 0)
        row["income"] = float(row["income"] or 0)
    return ApiResponse(success=True, data={
        "year": year, "month": mon,
        "total_hours": float(summary["total_hours"] or 0),
        "total_income": float(summary["total_income"] or 0),
        "session_count": int(summary["session_count"] or 0),
        "breakdown": breakdown,
    })


@router.get("/expense", summary="家長支出統計", response_model=ApiResponse)
def get_expense_stats(month: str = Query(None, pattern=r"^\d{4}-\d{2}$"), user=Depends(require_role("parent")), conn=Depends(get_db)):
    repo = PostgresStatsRepository(conn)
    year, mon = _parse_month(month)
    user_id = int(user["sub"])
    summary = repo.expense_summary(user_id, year, mon)
    breakdown = repo.expense_breakdown(user_id, year, mon)
    if summary is None:
        summary = {"total_hours": 0, "total_expense": 0, "session_count": 0}
    for row in breakdown:
        row["hours"] = float(row["hours"] or 0)
        row["expense"] = float(row["expense"] or 0)
    return ApiResponse(success=True, data={
        "year": year, "month": mon,
        "total_hours": float(summary["total_hours"] or 0),
        "total_expense": float(summary["total_expense"] or 0),
        "session_count": int(summary["session_count"] or 0),
        "breakdown": breakdown,
    })


@router.get("/student-progress/{student_id}", summary="學生成績趨勢", response_model=ApiResponse)
def get_student_progress(student_id: int, subject_id: int | None = Query(None), user=Depends(get_current_user), conn=Depends(get_db)):
    repo = PostgresStatsRepository(conn)
    user_id = int(user["sub"])
    student = repo.get_student(student_id)
    if not student:
        raise NotFoundError("找不到此學生")
    is_parent = student["parent_user_id"] == user_id
    is_tutor = bool(repo.get_active_match_for_tutor(student_id, user_id))
    if not is_parent and not is_tutor and not is_admin(user):
        raise PermissionDeniedError("無權查看此學生的成績資料")
    if is_tutor and not is_parent and not is_admin(user):
        tutor_subject_ids = repo.get_tutor_subject_ids_for_student(student_id, user_id)
        if subject_id is not None:
            if subject_id not in tutor_subject_ids:
                raise PermissionDeniedError("無權查看此科目的成績")
        else:
            exams = repo.student_progress_by_subjects(student_id, tutor_subject_ids)
            for row in exams:
                row["score"] = float(row["score"] or 0)
            return ApiResponse(success=True, data=exams)
    exams = repo.student_progress(student_id, subject_id)
    for row in exams:
        row["score"] = float(row["score"] or 0)
    return ApiResponse(success=True, data=exams)
