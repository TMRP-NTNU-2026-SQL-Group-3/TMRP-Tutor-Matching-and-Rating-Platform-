from pydantic import BaseModel, Field, model_validator

from app.review.domain.constants import LOW_RATING_MIN_COMMENT_LEN as _LOW_RATING_MIN_COMMENT_LEN
from app.review.domain.constants import LOW_RATING_THRESHOLD as _LOW_RATING_THRESHOLD


class ReviewCreateBody(BaseModel):
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
        if self.review_type == "parent_to_tutor":
            if any(r is None for r in ratings):
                raise ValueError("家長評老師需要填寫全部 4 項評分")
        if self.review_type in ("tutor_to_parent", "tutor_to_student"):
            r3_set = self.rating_3 is not None
            r4_set = self.rating_4 is not None
            if r3_set != r4_set:
                raise ValueError("rating_3 與 rating_4 需同時填寫或同時留空")
        if any(r is not None and r <= _LOW_RATING_THRESHOLD for r in ratings):
            body = (self.comment or "").strip()
            if len(body) < _LOW_RATING_MIN_COMMENT_LEN:
                raise ValueError(
                    f"評分 {_LOW_RATING_THRESHOLD} 星以下時必須填寫 "
                    f"至少 {_LOW_RATING_MIN_COMMENT_LEN} 字的文字說明"
                )
        return self


class ReviewCreate(ReviewCreateBody):
    match_id: int = Field(..., description="配對 ID")


class ReviewUpdate(BaseModel):
    rating_1: int | None = Field(default=None, ge=1, le=5)
    rating_2: int | None = Field(default=None, ge=1, le=5)
    rating_3: int | None = Field(default=None, ge=1, le=5)
    rating_4: int | None = Field(default=None, ge=1, le=5)
    personality_comment: str | None = Field(default=None, max_length=5000)
    comment: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _prevent_rating_nullification(self):
        for field in ("rating_1", "rating_2", "rating_3", "rating_4"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError("評分欄位不可設為 null；如不修改請省略此欄位")
        return self

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
