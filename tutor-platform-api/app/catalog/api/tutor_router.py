from enum import Enum

from fastapi import APIRouter, Depends, Query

from app.catalog.api.dependencies import get_tutor_repo, get_tutor_service
from app.catalog.api.schemas import AvailabilityUpdate, SubjectUpdate, TutorProfileUpdate, VisibilityUpdate
from app.catalog.domain.services import TutorService
from app.catalog.infrastructure.postgres_subject_repo import PostgresSubjectRepository
from app.catalog.infrastructure.postgres_tutor_repo import PostgresTutorRepository
from app.identity.api.dependencies import get_current_user, get_db, require_role
from app.shared.api.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.shared.api.schemas import ApiResponse
from app.shared.domain.exceptions import DomainException, NotFoundError

router = APIRouter(prefix="/api/tutors", tags=["tutors"])


class SortBy(str, Enum):
    rating = "rating"
    rate_asc = "rate_asc"
    newest = "newest"


@router.get("/me", summary="取得自己的老師檔案", description="取得目前登入老師的完整個人檔案，包含科目與可用時段。僅限老師角色。", response_model=ApiResponse)
def get_my_profile(
    user=Depends(require_role("tutor")),
    repo: PostgresTutorRepository = Depends(get_tutor_repo),
):
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
    sort_by: SortBy = Query(SortBy.rating),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    user=Depends(get_current_user),
    repo: PostgresTutorRepository = Depends(get_tutor_repo),
    service: TutorService = Depends(get_tutor_service),
):
    rows, total = repo.search_with_stats(
        subject_id=subject_id, school=school,
        min_rate=min_rate, max_rate=max_rate, min_rating=min_rating,
        sort_by=sort_by.value, page=page, page_size=page_size,
    )

    results = [
        service.apply_visibility(service.normalize_search_row(t))
        for t in rows
    ]

    total_pages = max(1, (total + page_size - 1) // page_size)
    return ApiResponse(
        success=True,
        data={
            "items": results,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    )


@router.put("/profile", summary="更新老師個人資料", response_model=ApiResponse)
def update_profile(
    body: TutorProfileUpdate,
    user=Depends(require_role("tutor")),
    repo: PostgresTutorRepository = Depends(get_tutor_repo),
):
    tutor = repo.find_by_user_id(int(user["sub"]))
    if not tutor:
        raise NotFoundError("找不到老師資料")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise DomainException("沒有提供任何要更新的欄位")
    repo.update_profile(tutor["tutor_id"], **fields)
    return ApiResponse(success=True, message="個人檔案更新成功")


@router.put("/profile/subjects", summary="設定可教授科目", response_model=ApiResponse)
def update_subjects(
    body: SubjectUpdate,
    user=Depends(require_role("tutor")),
    conn=Depends(get_db),
    repo: PostgresTutorRepository = Depends(get_tutor_repo),
):
    tutor = repo.find_by_user_id(int(user["sub"]))
    if not tutor:
        raise NotFoundError("找不到老師資料")
    if body.subjects:
        valid_ids = PostgresSubjectRepository(conn).list_subject_ids()
        for s in body.subjects:
            if s.subject_id not in valid_ids:
                raise DomainException(f"科目 ID {s.subject_id} 不存在")
    items = [s.model_dump() for s in body.subjects]
    repo.replace_subjects(tutor["tutor_id"], items)
    return ApiResponse(success=True, message="科目設定已更新")


@router.put("/profile/availability", summary="設定可用時段", response_model=ApiResponse)
def update_availability(
    body: AvailabilityUpdate,
    user=Depends(require_role("tutor")),
    repo: PostgresTutorRepository = Depends(get_tutor_repo),
):
    tutor = repo.find_by_user_id(int(user["sub"]))
    if not tutor:
        raise NotFoundError("找不到老師資料")
    slots = [s.model_dump() for s in body.slots]
    repo.replace_availability(tutor["tutor_id"], slots)
    return ApiResponse(success=True, message="可用時段已更新")


@router.put("/profile/visibility", summary="更新欄位公開設定", response_model=ApiResponse)
def update_visibility(
    body: VisibilityUpdate,
    user=Depends(require_role("tutor")),
    repo: PostgresTutorRepository = Depends(get_tutor_repo),
):
    tutor = repo.find_by_user_id(int(user["sub"]))
    if not tutor:
        raise NotFoundError("找不到老師資料")
    flags = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not flags:
        raise DomainException("沒有提供任何要更新的欄位")
    repo.update_visibility(tutor["tutor_id"], flags)
    return ApiResponse(success=True, message="公開設定已更新")


@router.get("/{tutor_id}", summary="取得老師詳情", response_model=ApiResponse)
def get_tutor_detail(
    tutor_id: int,
    user=Depends(get_current_user),
    repo: PostgresTutorRepository = Depends(get_tutor_repo),
    service: TutorService = Depends(get_tutor_service),
):
    tutor = repo.find_detail(tutor_id)
    if not tutor:
        raise NotFoundError("找不到此老師")
    tutor["rating"] = {
        "avg_r1": tutor.pop("avg_r1"),
        "avg_r2": tutor.pop("avg_r2"),
        "avg_r3": tutor.pop("avg_r3"),
        "avg_r4": tutor.pop("avg_r4"),
        "review_count": tutor.pop("review_count"),
    }
    if int(user["sub"]) != tutor["user_id"]:
        tutor = service.apply_visibility(tutor)
    return ApiResponse(success=True, data=tutor)


@router.get("/{tutor_id}/reviews", summary="取得老師評價", response_model=ApiResponse)
def get_tutor_reviews(
    tutor_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    user=Depends(get_current_user),
    conn=Depends(get_db),
    repo: PostgresTutorRepository = Depends(get_tutor_repo),
):
    tutor = repo.find_by_id(tutor_id)
    if not tutor:
        raise NotFoundError("找不到此老師")
    # MEDIUM-8: bounded fetch + public-field projection happens in the repo.
    from app.review.infrastructure.postgres_review_repo import PostgresReviewRepository
    review_repo = PostgresReviewRepository(conn)
    offset = (page - 1) * page_size
    reviews = review_repo.list_by_tutor(tutor_id, limit=page_size, offset=offset)
    total = review_repo.count_by_tutor(tutor_id)
    total_pages = max(1, (total + page_size - 1) // page_size)
    return ApiResponse(
        success=True,
        data={
            "items": reviews,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    )
