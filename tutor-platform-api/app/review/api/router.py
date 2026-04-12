from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from app.identity.api.dependencies import get_current_user, get_db, is_admin
from app.review.api.schemas import ReviewCreate, ReviewUpdate
from app.review.infrastructure.postgres_review_repo import PostgresReviewRepository
from app.shared.api.schemas import ApiResponse
from app.shared.domain.exceptions import ConflictError, DomainException, NotFoundError, PermissionDeniedError
from app.shared.infrastructure.config import settings
from app.shared.infrastructure.database_tx import transaction

router = APIRouter(prefix="/api/reviews", tags=["reviews"])

VALID_TYPES = {"parent_to_tutor", "tutor_to_parent", "tutor_to_student"}


@router.post("", summary="新增評價", response_model=ApiResponse)
def create_review(body: ReviewCreate, user=Depends(get_current_user), conn=Depends(get_db)):
    repo = PostgresReviewRepository(conn)
    user_id = int(user["sub"])
    if body.review_type not in VALID_TYPES:
        raise DomainException("評價類型必須為 parent_to_tutor、tutor_to_parent 或 tutor_to_student")
    match = repo.get_match_for_create(body.match_id)
    if not match:
        raise NotFoundError("找不到此配對")
    REVIEWABLE_STATUSES = {'active', 'paused', 'ended'}
    if match["status"] not in REVIEWABLE_STATUSES:
        raise DomainException("只能對進行中或已結束的配對提交評價")
    is_parent = match["parent_user_id"] == user_id
    is_tutor = match["tutor_user_id"] == user_id
    if body.review_type == "parent_to_tutor" and not is_parent:
        raise PermissionDeniedError("只有家長可以評價老師")
    if body.review_type in ("tutor_to_parent", "tutor_to_student") and not is_tutor:
        raise PermissionDeniedError("只有老師可以評價家長或學生")
    with transaction(conn):
        if repo.find_existing(body.match_id, user_id, body.review_type):
            raise ConflictError("您已對此配對提交過同類型的評價")
        review_id = repo.create(
            match_id=body.match_id, reviewer_user_id=user_id,
            review_type=body.review_type, rating_1=body.rating_1,
            rating_2=body.rating_2, rating_3=body.rating_3,
            rating_4=body.rating_4, personality_comment=body.personality_comment,
            comment=body.comment,
        )
    return ApiResponse(success=True, data={"review_id": review_id}, message="評價已提交")


@router.get("", summary="列出配對評價", response_model=ApiResponse)
def list_reviews(match_id: int = Query(...), user=Depends(get_current_user), conn=Depends(get_db)):
    repo = PostgresReviewRepository(conn)
    user_id = int(user["sub"])
    match = repo.get_match_participants(match_id)
    if not match:
        raise NotFoundError("找不到此配對")
    is_participant = match["tutor_user_id"] == user_id or match["parent_user_id"] == user_id
    if not is_participant and not is_admin(user):
        raise PermissionDeniedError("無權查看此配對的評價")
    reviews = repo.list_by_match(match_id)
    return ApiResponse(success=True, data=reviews)


@router.patch("/{review_id}", summary="修改評價", response_model=ApiResponse)
def update_review(review_id: int, body: ReviewUpdate, user=Depends(get_current_user), conn=Depends(get_db)):
    repo = PostgresReviewRepository(conn)
    user_id = int(user["sub"])
    review = repo.get_for_update(review_id)
    if not review:
        raise NotFoundError("找不到此評價")
    if review["reviewer_user_id"] != user_id:
        raise PermissionDeniedError("只有評價者本人可以修改評價")
    if review["is_locked"]:
        raise DomainException("評價已超過編輯期限，無法修改")
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.review_lock_days)
    created_at = review["created_at"]
    if hasattr(created_at, 'tzinfo') and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if created_at < cutoff:
        raise DomainException("評價已超過編輯期限，無法修改")
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return ApiResponse(success=True, data={}, message="無需更新的欄位")
    repo.update(review_id, updates)
    return ApiResponse(success=True, data={"review_id": review_id}, message="評價已更新")
