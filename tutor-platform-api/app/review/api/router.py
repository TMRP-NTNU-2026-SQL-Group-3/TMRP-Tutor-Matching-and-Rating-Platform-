import logging

from fastapi import APIRouter, Depends

from app.identity.api.dependencies import get_current_user, get_db, is_admin
from app.review.api.schemas import ReviewCreate, ReviewCreateBody, ReviewUpdate
from app.review.application.review_service import ReviewAppService
from app.review.domain.exceptions import NotMatchParticipantError, ReviewMatchNotFoundError
from app.review.infrastructure.postgres_review_repo import PostgresReviewRepository
from app.shared.api.schemas import ApiResponse
from app.shared.infrastructure.postgres_unit_of_work import PostgresUnitOfWork

logger = logging.getLogger("app.review")

# Spec §7.8: POST/GET /api/matches/{match_id}/reviews
match_reviews_router = APIRouter(prefix="/api/matches", tags=["reviews"])
# Remaining review-specific routes stay under /api/reviews
router = APIRouter(prefix="/api/reviews", tags=["reviews"])


def _get_review_service(conn=Depends(get_db)) -> ReviewAppService:
    return ReviewAppService(
        repo=PostgresReviewRepository(conn),
        uow=PostgresUnitOfWork(conn),
    )


@match_reviews_router.post("/{match_id}/reviews", status_code=201, summary="新增評價", response_model=ApiResponse)
def create_review(
    match_id: int,
    body: ReviewCreateBody,
    user=Depends(get_current_user),
    service: ReviewAppService = Depends(_get_review_service),
):
    full_body = ReviewCreate(match_id=match_id, **body.model_dump())
    review_id = service.create_review(user_id=int(user["sub"]), body=full_body)
    return ApiResponse(success=True, data={"review_id": review_id}, message="評價已提交")


@match_reviews_router.get("/{match_id}/reviews", summary="列出配對評價", response_model=ApiResponse)
def list_reviews(
    match_id: int,
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    repo = PostgresReviewRepository(conn)
    user_id = int(user["sub"])
    match = repo.get_match_participants(match_id)
    if not match:
        raise ReviewMatchNotFoundError()
    is_participant = match["tutor_user_id"] == user_id or match["parent_user_id"] == user_id
    if not is_participant and not is_admin(user):
        raise NotMatchParticipantError()
    reviews = repo.list_by_match(match_id)
    return ApiResponse(success=True, data=reviews)


@router.patch("/{review_id}", summary="修改評價", response_model=ApiResponse)
def update_review(
    review_id: int,
    body: ReviewUpdate,
    user=Depends(get_current_user),
    service: ReviewAppService = Depends(_get_review_service),
):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return ApiResponse(success=True, data={}, message="無需更新的欄位")
    service.update_review(user_id=int(user["sub"]), review_id=review_id, updates=updates)
    return ApiResponse(success=True, data={"review_id": review_id}, message="評價已更新")
