from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from app.teaching.domain.constants import EXAM_TYPES


def _check_exam_type(v: str) -> str:
    # Source of truth for allowed values is EXAM_TYPES; the DB CHECK
    # constraint in init_db.py is generated from the same tuple, so the
    # Pydantic layer and the database can never silently drift.
    if v not in EXAM_TYPES:
        raise ValueError(f"exam_type 必須為 {list(EXAM_TYPES)} 之一")
    return v


ExamType = Annotated[str, AfterValidator(_check_exam_type)]


class SessionCreateBody(BaseModel):
    session_date: datetime = Field(..., description="上課日期時間")
    hours: float = Field(..., gt=0, le=24, description="上課時數")
    content_summary: str = Field(..., max_length=4000, description="上課內容摘要")
    homework: str | None = Field(default=None, max_length=4000, description="指派作業")
    student_performance: str | None = Field(default=None, max_length=4000, description="學生表現紀錄")
    next_plan: str | None = Field(default=None, max_length=4000, description="下次上課計畫")
    visible_to_parent: bool = Field(default=False, description="是否對家長可見")


class SessionCreate(SessionCreateBody):
    match_id: int = Field(..., description="配對 ID")


class SessionUpdate(BaseModel):
    session_date: datetime | None = Field(default=None)
    hours: float | None = Field(default=None, gt=0, le=24)
    content_summary: str | None = Field(default=None, max_length=4000)
    homework: str | None = Field(default=None, max_length=4000)
    student_performance: str | None = Field(default=None, max_length=4000)
    next_plan: str | None = Field(default=None, max_length=4000)
    visible_to_parent: bool | None = Field(default=None)


class ExamCreateBody(BaseModel):
    subject_id: int = Field(..., description="科目 ID")
    exam_date: datetime = Field(..., description="考試日期")
    exam_type: ExamType = Field(..., description="考試類型")
    score: float = Field(..., ge=0, le=150, description="考試分數")
    visible_to_parent: bool = Field(default=True, description="是否對家長可見")


class ExamCreate(ExamCreateBody):
    student_id: int = Field(..., description="學生 ID")


class ExamUpdate(BaseModel):
    exam_date: datetime | None = Field(default=None)
    exam_type: ExamType | None = Field(default=None)
    score: float | None = Field(default=None, ge=0, le=150)
    visible_to_parent: bool | None = Field(default=None)
