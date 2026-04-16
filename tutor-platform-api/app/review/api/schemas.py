from pydantic import BaseModel, Field, model_validator


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
    def _require_all_ratings_for_parent_to_tutor(self):
        # parent_to_tutor feeds the public 4-axis tutor average; missing axes would
        # skew AVG() in get_avg_rating, so all four ratings are mandatory there.
        if self.review_type == "parent_to_tutor":
            if any(r is None for r in (self.rating_1, self.rating_2, self.rating_3, self.rating_4)):
                raise ValueError("家長評老師需要填寫全部 4 項評分")
        return self


class ReviewUpdate(BaseModel):
    rating_1: int | None = Field(default=None, ge=1, le=5)
    rating_2: int | None = Field(default=None, ge=1, le=5)
    rating_3: int | None = Field(default=None, ge=1, le=5)
    rating_4: int | None = Field(default=None, ge=1, le=5)
    personality_comment: str | None = Field(default=None, max_length=5000)
    comment: str | None = Field(default=None, max_length=5000)
