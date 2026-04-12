from pydantic import BaseModel, Field


class ReviewCreate(BaseModel):
    match_id: int = Field(..., description="配對 ID")
    review_type: str = Field(..., description="評價類型")
    rating_1: int = Field(ge=1, le=5)
    rating_2: int = Field(ge=1, le=5)
    rating_3: int | None = Field(default=None, ge=1, le=5)
    rating_4: int | None = Field(default=None, ge=1, le=5)
    personality_comment: str | None = Field(default=None)
    comment: str | None = Field(default=None)


class ReviewUpdate(BaseModel):
    rating_1: int | None = Field(default=None, ge=1, le=5)
    rating_2: int | None = Field(default=None, ge=1, le=5)
    rating_3: int | None = Field(default=None, ge=1, le=5)
    rating_4: int | None = Field(default=None, ge=1, le=5)
    personality_comment: str | None = Field(default=None)
    comment: str | None = Field(default=None)
