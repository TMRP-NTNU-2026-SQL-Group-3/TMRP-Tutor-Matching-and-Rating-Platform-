from fastapi import APIRouter, Depends, Query

from app.dependencies import get_current_user, get_db, require_role
from app.exceptions import AppException, NotFoundException
from app.models.common import ApiResponse
from app.models.tutor import AvailabilityUpdate, SubjectUpdate, TutorProfileUpdate, VisibilityUpdate
from app.repositories.review_repo import ReviewRepository
from app.repositories.tutor_repo import TutorRepository

router = APIRouter(prefix="/api/tutors", tags=["tutors"])


def _apply_visibility(tutor: dict) -> dict:
    """根據老師的隱私設定，遮蔽不公開的欄位。"""
    if not tutor.get("show_university"):
        tutor.pop("university", None)
    if not tutor.get("show_department"):
        tutor.pop("department", None)
    if not tutor.get("show_grade_year"):
        tutor.pop("grade_year", None)
    return tutor


# ── 靜態路徑（必須放在 /{tutor_id} 之前） ──────────────────────

@router.get("/me", response_model=ApiResponse)
def get_my_profile(
    user=Depends(require_role("tutor")),
    conn=Depends(get_db),
):
    repo = TutorRepository(conn)
    tutor = repo.find_by_user_id(int(user["sub"]))
    if not tutor:
        raise NotFoundException("找不到老師資料")
    tutor["subjects"] = repo.get_subjects(tutor["tutor_id"])
    tutor["availability"] = repo.get_availability(tutor["tutor_id"])
    return ApiResponse(success=True, data=tutor)


@router.get("", response_model=ApiResponse)
def search_tutors(
    subject_id: int = Query(None),
    min_rate: float = Query(None),
    max_rate: float = Query(None),
    min_rating: float = Query(None),
    school: str = Query(None),
    sort_by: str = Query("rating"),
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    repo = TutorRepository(conn)
    tutors = repo.search(subject_id=subject_id, school=school)

    results = []
    for t in tutors:
        subjects = repo.get_subjects(t["tutor_id"])
        rating = repo.get_avg_rating(t["tutor_id"])

        # 計算平均時薪（所有科目）
        rates = [s["hourly_rate"] for s in subjects if s.get("hourly_rate")]
        avg_rate = sum(rates) / len(rates) if rates else 0

        # min/max rate 過濾
        if min_rate is not None and avg_rate < min_rate:
            continue
        if max_rate is not None and avg_rate > max_rate:
            continue

        # 平均評分
        avg_rating_val = 0
        review_count = 0
        if rating and rating.get("review_count"):
            review_count = rating["review_count"]
            vals = [rating.get(f"avg_r{i}") for i in range(1, 5) if rating.get(f"avg_r{i}") is not None]
            avg_rating_val = sum(vals) / len(vals) if vals else 0

        if min_rating is not None and avg_rating_val < min_rating:
            continue

        t["subjects"] = subjects if t.get("show_subjects", True) else []
        if not t.get("show_hourly_rate", True):
            for s in t.get("subjects", []):
                s.pop("hourly_rate", None)
        t["avg_rating"] = round(avg_rating_val, 2)
        t["review_count"] = review_count
        _apply_visibility(t)
        results.append(t)

    # 排序
    if sort_by == "rate_asc":
        results.sort(key=lambda x: sum(s["hourly_rate"] for s in x.get("subjects", []) if s.get("hourly_rate")) or 0)
    elif sort_by == "newest":
        results.sort(key=lambda x: x.get("tutor_id", 0), reverse=True)
    else:
        results.sort(key=lambda x: x.get("avg_rating", 0), reverse=True)

    return ApiResponse(success=True, data=results)


@router.put("/profile", response_model=ApiResponse)
def update_profile(
    body: TutorProfileUpdate,
    user=Depends(require_role("tutor")),
    conn=Depends(get_db),
):
    repo = TutorRepository(conn)
    tutor = repo.find_by_user_id(int(user["sub"]))
    if not tutor:
        raise NotFoundException("找不到老師資料")

    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise AppException("沒有提供任何要更新的欄位")

    repo.update_profile(tutor["tutor_id"], **fields)
    return ApiResponse(success=True, message="個人檔案更新成功")


@router.put("/profile/subjects", response_model=ApiResponse)
def update_subjects(
    body: SubjectUpdate,
    user=Depends(require_role("tutor")),
    conn=Depends(get_db),
):
    """整批替換老師的可教授科目與時薪。"""
    repo = TutorRepository(conn)
    tutor = repo.find_by_user_id(int(user["sub"]))
    if not tutor:
        raise NotFoundException("找不到老師資料")

    # 驗證所有 subject_id 皆存在
    if body.subjects:
        from app.repositories.base import BaseRepository
        base = BaseRepository(conn)
        all_subjects = base.fetch_all("SELECT subject_id FROM Subjects")
        valid_ids = {s["subject_id"] for s in all_subjects}
        for s in body.subjects:
            if s.subject_id not in valid_ids:
                raise AppException(f"科目 ID {s.subject_id} 不存在")

    items = [s.model_dump() for s in body.subjects]
    repo.replace_subjects(tutor["tutor_id"], items)
    return ApiResponse(success=True, message="科目設定已更新")


@router.put("/profile/availability", response_model=ApiResponse)
def update_availability(
    body: AvailabilityUpdate,
    user=Depends(require_role("tutor")),
    conn=Depends(get_db),
):
    """整批替換老師的可用時段。"""
    repo = TutorRepository(conn)
    tutor = repo.find_by_user_id(int(user["sub"]))
    if not tutor:
        raise NotFoundException("找不到老師資料")

    slots = [s.model_dump() for s in body.slots]
    repo.replace_availability(tutor["tutor_id"], slots)
    return ApiResponse(success=True, message="可用時段已更新")


@router.put("/profile/visibility", response_model=ApiResponse)
def update_visibility(
    body: VisibilityUpdate,
    user=Depends(require_role("tutor")),
    conn=Depends(get_db),
):
    """更新老師的欄位公開設定。"""
    repo = TutorRepository(conn)
    tutor = repo.find_by_user_id(int(user["sub"]))
    if not tutor:
        raise NotFoundException("找不到老師資料")

    flags = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not flags:
        raise AppException("沒有提供任何要更新的欄位")

    repo.update_visibility(tutor["tutor_id"], flags)
    return ApiResponse(success=True, message="公開設定已更新")


# ── 動態路徑（/{tutor_id} 放在最後） ──────────────────────────

@router.get("/{tutor_id}", response_model=ApiResponse)
def get_tutor_detail(
    tutor_id: int,
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    repo = TutorRepository(conn)
    tutor = repo.find_by_id(tutor_id)
    if not tutor:
        raise NotFoundException("找不到此老師")

    tutor["subjects"] = repo.get_subjects(tutor_id)
    tutor["availability"] = repo.get_availability(tutor_id)
    tutor["rating"] = repo.get_avg_rating(tutor_id)
    tutor["active_student_count"] = repo.get_active_student_count(tutor_id)

    # 如果查看者不是老師本人，套用隱私設定
    if int(user["sub"]) != tutor["user_id"]:
        _apply_visibility(tutor)
        if not tutor.get("show_subjects", True):
            tutor["subjects"] = []
        if not tutor.get("show_hourly_rate", True):
            for s in tutor.get("subjects", []):
                s.pop("hourly_rate", None)

    return ApiResponse(success=True, data=tutor)


@router.get("/{tutor_id}/reviews", response_model=ApiResponse)
def get_tutor_reviews(
    tutor_id: int,
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    """取得某位老師收到的所有 parent_to_tutor 評價。"""
    tutor_repo = TutorRepository(conn)
    tutor = tutor_repo.find_by_id(tutor_id)
    if not tutor:
        raise NotFoundException("找不到此老師")

    review_repo = ReviewRepository(conn)
    reviews = review_repo.list_by_tutor(tutor_id)
    return ApiResponse(success=True, data=reviews)
