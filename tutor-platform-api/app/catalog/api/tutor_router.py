from fastapi import APIRouter, Depends, Query

from app.catalog.api.schemas import AvailabilityUpdate, SubjectUpdate, TutorProfileUpdate, VisibilityUpdate
from app.catalog.domain.services import TutorService
from app.catalog.infrastructure.postgres_tutor_repo import PostgresTutorRepository
from app.identity.api.dependencies import get_current_user, get_db, require_role
from app.shared.api.schemas import ApiResponse
from app.shared.domain.exceptions import DomainException, NotFoundError

router = APIRouter(prefix="/api/tutors", tags=["tutors"])


def _build_repo(conn) -> PostgresTutorRepository:
    return PostgresTutorRepository(conn)


def _build_service(conn) -> TutorService:
    return TutorService(tutor_repo=_build_repo(conn))


@router.get("/me", summary="取得自己的老師檔案", description="取得目前登入老師的完整個人檔案，包含科目與可用時段。僅限老師角色。", response_model=ApiResponse)
def get_my_profile(user=Depends(require_role("tutor")), conn=Depends(get_db)):
    repo = _build_repo(conn)
    tutor = repo.find_by_user_id(int(user["sub"]))
    if not tutor:
        raise NotFoundError("找不到老師資料")
    tutor["subjects"] = repo.get_subjects(tutor["tutor_id"])
    tutor["availability"] = repo.get_availability(tutor["tutor_id"])
    return ApiResponse(success=True, data=tutor)


@router.get("", summary="搜尋老師", description="依科目、時薪範圍、評分、學校等條件搜尋老師。", response_model=ApiResponse)
def search_tutors(
    subject_id: int = Query(None),
    min_rate: float = Query(None),
    max_rate: float = Query(None),
    min_rating: float = Query(None),
    school: str = Query(None),
    sort_by: str = Query("rating"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    repo = _build_repo(conn)
    service = _build_service(conn)
    tutors = repo.search(subject_id=subject_id, school=school)

    results = []
    for t in tutors:
        subjects = repo.get_subjects(t["tutor_id"])
        rating = repo.get_avg_rating(t["tutor_id"])
        rates = [s["hourly_rate"] for s in subjects if s.get("hourly_rate")]
        avg_rate = sum(rates) / len(rates) if rates else 0
        if min_rate is not None and avg_rate < min_rate:
            continue
        if max_rate is not None and avg_rate > max_rate:
            continue

        avg_rating_val = 0
        review_count = 0
        if rating and rating.get("review_count"):
            review_count = rating["review_count"]
            vals = [rating.get(f"avg_r{i}") for i in range(1, 5) if rating.get(f"avg_r{i}") is not None]
            avg_rating_val = sum(vals) / len(vals) if vals else 0
        if min_rating is not None and avg_rating_val < min_rating:
            continue

        if not t.get("show_hourly_rate", True):
            for s in subjects:
                s.pop("hourly_rate", None)
        t["subjects"] = subjects if t.get("show_subjects", True) else []
        t["avg_rating"] = round(avg_rating_val, 2)
        t["review_count"] = review_count
        service.apply_visibility(t)
        results.append(t)

    if sort_by == "rate_asc":
        def _avg_rate(x):
            rates = [s["hourly_rate"] for s in x.get("subjects", []) if s.get("hourly_rate")]
            return (0 if rates else 1, sum(rates) / len(rates) if rates else float('inf'))
        results.sort(key=_avg_rate)
    elif sort_by == "newest":
        results.sort(key=lambda x: x.get("tutor_id", 0), reverse=True)
    else:
        results.sort(key=lambda x: x.get("avg_rating", 0), reverse=True)

    total = len(results)
    start = (page - 1) * page_size
    paginated = results[start:start + page_size]
    return ApiResponse(success=True, data={"items": paginated, "total": total})


@router.put("/profile", summary="更新老師個人資料", response_model=ApiResponse)
def update_profile(body: TutorProfileUpdate, user=Depends(require_role("tutor")), conn=Depends(get_db)):
    repo = _build_repo(conn)
    tutor = repo.find_by_user_id(int(user["sub"]))
    if not tutor:
        raise NotFoundError("找不到老師資料")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise DomainException("沒有提供任何要更新的欄位")
    repo.update_profile(tutor["tutor_id"], **fields)
    return ApiResponse(success=True, message="個人檔案更新成功")


@router.put("/profile/subjects", summary="設定可教授科目", response_model=ApiResponse)
def update_subjects(body: SubjectUpdate, user=Depends(require_role("tutor")), conn=Depends(get_db)):
    repo = _build_repo(conn)
    tutor = repo.find_by_user_id(int(user["sub"]))
    if not tutor:
        raise NotFoundError("找不到老師資料")
    if body.subjects:
        from app.shared.infrastructure.base_repository import BaseRepository
        base = BaseRepository(conn)
        all_subjects = base.fetch_all("SELECT subject_id FROM subjects")
        valid_ids = {s["subject_id"] for s in all_subjects}
        for s in body.subjects:
            if s.subject_id not in valid_ids:
                raise DomainException(f"科目 ID {s.subject_id} 不存在")
    items = [s.model_dump() for s in body.subjects]
    repo.replace_subjects(tutor["tutor_id"], items)
    return ApiResponse(success=True, message="科目設定已更新")


@router.put("/profile/availability", summary="設定可用時段", response_model=ApiResponse)
def update_availability(body: AvailabilityUpdate, user=Depends(require_role("tutor")), conn=Depends(get_db)):
    repo = _build_repo(conn)
    tutor = repo.find_by_user_id(int(user["sub"]))
    if not tutor:
        raise NotFoundError("找不到老師資料")
    slots = [s.model_dump() for s in body.slots]
    repo.replace_availability(tutor["tutor_id"], slots)
    return ApiResponse(success=True, message="可用時段已更新")


@router.put("/profile/visibility", summary="更新欄位公開設定", response_model=ApiResponse)
def update_visibility(body: VisibilityUpdate, user=Depends(require_role("tutor")), conn=Depends(get_db)):
    repo = _build_repo(conn)
    tutor = repo.find_by_user_id(int(user["sub"]))
    if not tutor:
        raise NotFoundError("找不到老師資料")
    flags = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not flags:
        raise DomainException("沒有提供任何要更新的欄位")
    repo.update_visibility(tutor["tutor_id"], flags)
    return ApiResponse(success=True, message="公開設定已更新")


@router.get("/{tutor_id}", summary="取得老師詳情", response_model=ApiResponse)
def get_tutor_detail(tutor_id: int, user=Depends(get_current_user), conn=Depends(get_db)):
    repo = _build_repo(conn)
    service = _build_service(conn)
    tutor = repo.find_by_id(tutor_id)
    if not tutor:
        raise NotFoundError("找不到此老師")
    tutor["subjects"] = repo.get_subjects(tutor_id)
    tutor["availability"] = repo.get_availability(tutor_id)
    tutor["rating"] = repo.get_avg_rating(tutor_id)
    tutor["active_student_count"] = repo.get_active_student_count(tutor_id)
    if int(user["sub"]) != tutor["user_id"]:
        if not tutor.get("show_hourly_rate", True):
            for s in tutor.get("subjects", []):
                s.pop("hourly_rate", None)
        if not tutor.get("show_subjects", True):
            tutor["subjects"] = []
        service.apply_visibility(tutor)
    return ApiResponse(success=True, data=tutor)


@router.get("/{tutor_id}/reviews", summary="取得老師評價", response_model=ApiResponse)
def get_tutor_reviews(tutor_id: int, user=Depends(get_current_user), conn=Depends(get_db)):
    repo = _build_repo(conn)
    tutor = repo.find_by_id(tutor_id)
    if not tutor:
        raise NotFoundError("找不到此老師")
    from app.review.infrastructure.postgres_review_repo import PostgresReviewRepository
    review_repo = PostgresReviewRepository(conn)
    reviews = review_repo.list_by_tutor(tutor_id)
    return ApiResponse(success=True, data=reviews)
