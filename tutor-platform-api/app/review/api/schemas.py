from pydantic import BaseModel, Field, model_validator

from app.review.domain.constants import LOW_RATING_MIN_COMMENT_LEN as _LOW_RATING_MIN_COMMENT_LEN
from app.review.domain.constants import LOW_RATING_THRESHOLD as _LOW_RATING_THRESHOLD


class ReviewCreate(BaseModel):
    match_id: int = Field(..., description="配對 ID")
    review_type: str = Field(..., description="評價類型")
    rating_1: int = Field(ge=1, le=5)
    rating_2: int = Field(ge=1, le=5)
    rating_3: int | None = Field(default=None, ge=1, le=5)
    rating_4: int | None = Field(default=None, ge=1, le=5)
    personality_comment: str | None = Field(default=None, max_length=5000)
    comment: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _validate_review_shape(self):
        ratings = (self.rating_1, self.rating_2, self.rating_3, self.rating_4)

        # parent_to_tutor feeds the public 4-axis tutor average; missing axes
        # would skew AVG() in get_avg_rating, so all four are mandatory there.
        if self.review_type == "parent_to_tutor":
            if any(r is None for r in ratings):
                raise ValueError("家長評老師需要填寫全部 4 項評分")

        # MEDIUM-9: tutor_to_parent / tutor_to_student accept optional
        # rating_3/rating_4, but only as a bundle. A partial fill (e.g.
        # rating_3 set, rating_4 null) skews any future aggregate on the
        # tutor-side review axes, so require all-or-none for the optional
        # pair. The required axes (rating_1, rating_2) remain as-is.
        if self.review_type in ("tutor_to_parent", "tutor_to_student"):
            r3_set = self.rating_3 is not None
            r4_set = self.rating_4 is not None
            if r3_set != r4_set:
                raise ValueError("rating_3 與 rating_4 需同時填寫或同時留空")

        # MEDIUM-9: any rating at or below the low-rating threshold must be
        # accompanied by a substantive comment. Without this, a one-star
        # review needs no justification, making retaliatory griefing free.
        if any(r is not None and r <= _LOW_RATING_THRESHOLD for r in ratings):
            body = (self.comment or "").strip()
            if len(body) < _LOW_RATING_MIN_COMMENT_LEN:
                raise ValueError(
                    f"評分 {_LOW_RATING_THRESHOLD} 星以下時必須填寫 "
                    f"至少 {_LOW_RATING_MIN_COMMENT_LEN} 字的文字說明"
                )

        return self


class ReviewUpdate(BaseModel):
    rating_1: int | None = Field(default=None, ge=1, le=5)
    rating_2: int | None = Field(default=None, ge=1, le=5)
    rating_3: int | None = Field(default=None, ge=1, le=5)
    rating_4: int | None = Field(default=None, ge=1, le=5)
    personality_comment: str | None = Field(default=None, max_length=5000)
    comment: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _validate_low_rating_requires_comment(self):
        # MEDIUM-9: same rule on edit. Without this, an attacker could create
        # a compliant 3-star review and then patch it down to 1-star with no
        # comment, neutering the create-time check.
        ratings = (self.rating_1, self.rating_2, self.rating_3, self.rating_4)
        if any(r is not None and r <= _LOW_RATING_THRESHOLD for r in ratings):
            # On update, `comment=None` means "leave unchanged", so we can't
            # enforce a hard minimum here without joining the stored row.
            # Instead, if the caller *does* send a comment in this patch,
            # require it to meet the floor; otherwise defer enforcement to
            # the service layer, which sees the merged record.
            if self.comment is not None:
                if len(self.comment.strip()) < _LOW_RATING_MIN_COMMENT_LEN:
                    raise ValueError(
                        f"評分 {_LOW_RATING_THRESHOLD} 星以下時必須填寫 "
                        f"至少 {_LOW_RATING_MIN_COMMENT_LEN} 字的文字說明"
                    )
        return self
