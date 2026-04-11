from fastapi import APIRouter, Depends, Query

from app.database_tx import transaction
from app.dependencies import get_current_user, get_db, is_admin
from app.exceptions import AppException, ConflictException, ForbiddenException, NotFoundException
from app.models.common import ApiResponse
from app.models.review import ReviewCreate, ReviewUpdate
from app.repositories.review_repo import ReviewRepository

router = APIRouter(prefix="/api/reviews", tags=["reviews"])

VALID_TYPES = {"parent_to_tutor", "tutor_to_parent", "tutor_to_student"}


@router.post("", summary="新增評價", description="建立三向評價（家長→老師、老師→家長、老師→學生）。每種類型對同一配對僅能提交一次。", response_model=ApiResponse)
def create_review(
    body: ReviewCreate,
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    repo = ReviewRepository(conn)
    user_id = int(user["sub"])

    if body.review_type not in VALID_TYPES:
        raise AppException("評價類型必須為 parent_to_tutor、tutor_to_parent 或 tutor_to_student")

    match = repo.get_match_for_create(body.match_id)
    if not match:
        raise NotFoundException("找不到此配對")

    # T-API-05: 移除 terminating，只允許確定狀態下提交評價
    REVIEWABLE_STATUSES = {'active', 'paused', 'ended'}
    if match["status"] not in REVIEWABLE_STATUSES:
        raise AppException("只能對進行中或已結束的配對提交評價")

    is_parent = match["parent_user_id"] == user_id
    is_tutor = match["tutor_user_id"] == user_id

    if body.review_type == "parent_to_tutor" and not is_parent:
        raise ForbiddenException("只有家長可以評價老師")
    if body.review_type in ("tutor_to_parent", "tutor_to_student") and not is_tutor:
        raise ForbiddenException("只有老師可以評價家長或學生")

    # T-API-02: 將重複檢查與 INSERT 包入同一交易，防止 TOCTOU 競態條件
    with transaction(conn):
        if repo.find_existing(body.match_id, user_id, body.review_type):
            raise ConflictException("您已對此配對提交過同類型的評價")

        review_id = repo.create(
            match_id=body.match_id,
            reviewer_user_id=user_id,
            review_type=body.review_type,
            rating_1=body.rating_1,
            rating_2=body.rating_2,
            rating_3=body.rating_3,
            rating_4=body.rating_4,
            personality_comment=body.personality_comment,
            comment=body.comment,
        )
    return ApiResponse(success=True, data={"review_id": review_id}, message="評價已提交")


@router.get("", summary="列出配對評價", description="列出指定配對的所有評價，包含評價者姓名。僅限配對參與者或管理員。", response_model=ApiResponse)
def list_reviews(
    match_id: int = Query(...),
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    repo = ReviewRepository(conn)
    user_id = int(user["sub"])

    match = repo.get_match_participants(match_id)
    if not match:
        raise NotFoundException("找不到此配對")

    is_participant = match["tutor_user_id"] == user_id or match["parent_user_id"] == user_id
    if not is_participant and not is_admin(user):
        raise ForbiddenException("無權查看此配對的評價")

    reviews = repo.list_by_match(match_id)
    return ApiResponse(success=True, data=reviews)


@router.patch("/{review_id}", summary="修改評價", description="修改已提交的評價，僅限評價者本人且在 7 天編輯期限內。超過期限後評價將自動鎖定。", response_model=ApiResponse)
def update_review(
    review_id: int,
    body: ReviewUpdate,
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    repo = ReviewRepository(conn)
    user_id = int(user["sub"])

    review = repo.get_for_update(review_id)
    if not review:
        raise NotFoundException("找不到此評價")
    if review["reviewer_user_id"] != user_id:
        raise ForbiddenException("只有評價者本人可以修改評價")
    if review["is_locked"]:
        raise AppException("評價已超過 7 天編輯期限，無法修改")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return ApiResponse(success=True, data={}, message="無需更新的欄位")

    repo.update(review_id, updates)
    return ApiResponse(success=True, data={"review_id": review_id}, message="評價已更新")
