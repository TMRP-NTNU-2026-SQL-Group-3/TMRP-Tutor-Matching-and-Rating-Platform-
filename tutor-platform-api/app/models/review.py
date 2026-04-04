from pydantic import BaseModel, Field


class ReviewCreate(BaseModel):
    match_id: int = Field(..., description="配對 ID", examples=[1])
    review_type: str = Field(..., description="評價類型（parent_to_tutor, tutor_to_student, tutor_to_parent）", examples=["parent_to_tutor"])
    rating_1: int = Field(ge=1, le=5, description="評分項目一（1-5 分）", examples=[5])
    rating_2: int = Field(ge=1, le=5, description="評分項目二（1-5 分）", examples=[4])
    rating_3: int | None = Field(default=None, ge=1, le=5, description="評分項目三（1-5 分，選填）", examples=[4])
    rating_4: int | None = Field(default=None, ge=1, le=5, description="評分項目四（1-5 分，選填）", examples=[3])
    personality_comment: str | None = Field(default=None, description="人格特質評語", examples=["很有耐心，教學認真"])
    comment: str | None = Field(default=None, description="整體評論", examples=["孩子進步很多，非常推薦"])


class ReviewUpdate(BaseModel):
    rating_1: int | None = Field(default=None, ge=1, le=5, description="評分項目一（1-5 分）", examples=[5])
    rating_2: int | None = Field(default=None, ge=1, le=5, description="評分項目二（1-5 分）", examples=[4])
    rating_3: int | None = Field(default=None, ge=1, le=5, description="評分項目三（1-5 分，選填）", examples=[4])
    rating_4: int | None = Field(default=None, ge=1, le=5, description="評分項目四（1-5 分，選填）", examples=[3])
    personality_comment: str | None = Field(default=None, description="人格特質評語", examples=["很有耐心，教學認真"])
    comment: str | None = Field(default=None, description="整體評論", examples=["孩子進步很多，非常推薦"])
