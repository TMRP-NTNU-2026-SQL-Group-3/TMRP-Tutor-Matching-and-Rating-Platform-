import logging
from datetime import datetime, timedelta, timezone

from psycopg2.errors import UniqueViolation

from app.review.domain.constants import LOW_RATING_MIN_COMMENT_LEN, LOW_RATING_THRESHOLD
from app.review.domain.exceptions import (
    DuplicateReviewError,
    InvalidReviewTypeError,
    LowRatingCommentRequiredError,
    MatchHasNoSessionsError,
    MatchNotReviewableError,
    NotReviewOwnerError,
    ReviewLockedError,
    ReviewMatchNotFoundError,
    ReviewNotFoundError,
    SelfReviewError,
    WrongReviewerRoleError,
)
from app.review.domain.ports import IReviewRepository
from app.shared.domain.ports import IUnitOfWork
from app.shared.infrastructure.config import settings

logger = logging.getLogger("app.review")

_VALID_TYPES = frozenset({"parent_to_tutor", "tutor_to_parent", "tutor_to_student"})
_REVIEWABLE_STATUSES = frozenset({"active", "paused", "ended"})


class ReviewAppService:
    def __init__(self, repo: IReviewRepository, uow: IUnitOfWork):
        self._repo = repo
        self._uow = uow

    def create_review(self, *, user_id: int, body) -> int:
        if body.review_type not in _VALID_TYPES:
            raise InvalidReviewTypeError()
        match = self._repo.get_match_for_create(body.match_id)
        if not match:
            raise ReviewMatchNotFoundError()
        if match["status"] not in _REVIEWABLE_STATUSES:
            raise MatchNotReviewableError()
        if match["session_count"] == 0:
            raise MatchHasNoSessionsError()
        is_parent = match["parent_user_id"] == user_id
        is_tutor = match["tutor_user_id"] == user_id
        if body.review_type == "parent_to_tutor" and not is_parent:
            raise WrongReviewerRoleError(body.review_type)
        if body.review_type in ("tutor_to_parent", "tutor_to_student") and not is_tutor:
            raise WrongReviewerRoleError(body.review_type)
        # S-03: a user holding both roles on the same match (parent_user_id ==
        # tutor_user_id) would pass either role check above and submit a
        # self-review. Block it explicitly before we reach the DB.
        if is_parent and is_tutor:
            raise SelfReviewError()
        # Rely on idx_reviews_unique (match_id, reviewer_user_id, review_type)
        # to enforce "one review per reviewer per type per match" atomically at
        # the DB layer. A prior find_existing + INSERT pair was racy — two
        # concurrent submissions could both see "no duplicate" and insert twice.
        try:
            with self._uow.begin():
                # ARCH-6: re-query session_count inside the transaction so a
                # concurrent session deletion between the outer read and this
                # INSERT cannot create a review on a match with no teaching history.
                live_match = self._repo.get_match_for_create(body.match_id)
                if not live_match or live_match["session_count"] == 0:
                    raise MatchHasNoSessionsError()
                return self._repo.create(
                    match_id=body.match_id, reviewer_user_id=user_id,
                    review_type=body.review_type, rating_1=body.rating_1,
                    rating_2=body.rating_2, rating_3=body.rating_3,
                    rating_4=body.rating_4, personality_comment=body.personality_comment,
                    comment=body.comment,
                )
        except UniqueViolation:
            raise DuplicateReviewError() from None

    def update_review(self, *, user_id: int, review_id: int, updates: dict) -> None:
        with self._uow.begin():
            review = self._repo.get_for_update(review_id)
            if not review:
                raise ReviewNotFoundError()
            if review["reviewer_user_id"] != user_id:
                raise NotReviewOwnerError()
            if review["is_locked"]:
                raise ReviewLockedError()
            cutoff = datetime.now(timezone.utc) - timedelta(days=settings.review_lock_days)
            created_at = review["created_at"]
            # created_at is TIMESTAMPTZ so psycopg2 returns an aware datetime;
            # the naive-fallback branch guards legacy rows imported before the
            # tzinfo migration. Any TypeError from the final compare maps to
            # ReviewLockedError (HTTP 400) rather than a bare 500 — refusing
            # the edit is safer than silently allowing it when we cannot prove
            # the row is inside the edit window.
            if isinstance(created_at, datetime) and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            try:
                past_cutoff = created_at < cutoff
            except TypeError as exc:
                # S-H4: log before swallowing so data-integrity issues surface in
                # structured logs rather than silently resolving to a lock refusal.
                logger.error(
                    "Unexpected created_at type in review lock check: %s (value=%r, review_id=%s)",
                    exc, created_at, review_id,
                )
                raise ReviewLockedError() from exc
            if past_cutoff:
                raise ReviewLockedError()
            # MEDIUM-9: enforce low-rating comment rule on partial updates.
            # The schema only validates when `comment` is explicitly sent; if the
            # caller omits it, the merged comment (stored value + no new value)
            # must still satisfy the floor. Fetch the stored comment here so we
            # can evaluate the combined state before writing.
            merged_ratings = {
                "rating_1": updates.get("rating_1", review.get("rating_1")),
                "rating_2": updates.get("rating_2", review.get("rating_2")),
                "rating_3": updates.get("rating_3", review.get("rating_3")),
                "rating_4": updates.get("rating_4", review.get("rating_4")),
            }
            if any(r is not None and r <= LOW_RATING_THRESHOLD for r in merged_ratings.values()):
                merged_comment = (updates.get("comment") or review.get("comment") or "").strip()
                if len(merged_comment) < LOW_RATING_MIN_COMMENT_LEN:
                    raise LowRatingCommentRequiredError(
                        threshold=LOW_RATING_THRESHOLD,
                        min_len=LOW_RATING_MIN_COMMENT_LEN,
                    )
            self._repo.update(review_id, updates)
