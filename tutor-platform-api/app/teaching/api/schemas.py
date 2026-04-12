from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    match_id: int = Field(..., description="配對 ID")
    session_date: datetime = Field(..., description="上課日期時間")
    hours: float = Field(..., gt=0, le=24, description="上課時數")
    content_summary: str = Field(..., description="上課內容摘要")
    homework: str | None = Field(default=None, description="指派作業")
    student_performance: str | None = Field(default=None, description="學生表現紀錄")
    next_plan: str | None = Field(default=None, description="下次上課計畫")
    visible_to_parent: bool = Field(default=False, description="是否對家長可見")


class SessionUpdate(BaseModel):
    session_date: datetime | None = Field(default=None)
    hours: float | None = Field(default=None, gt=0, le=24)
    content_summary: str | None = Field(default=None)
    homework: str | None = Field(default=None)
    student_performance: str | None = Field(default=None)
    next_plan: str | None = Field(default=None)
    visible_to_parent: bool | None = Field(default=None)


class ExamCreate(BaseModel):
    student_id: int = Field(..., description="學生 ID")
    subject_id: int = Field(..., description="科目 ID")
    exam_date: datetime = Field(..., description="考試日期")
    exam_type: str = Field(..., description="考試類型")
    score: float = Field(..., ge=0, description="考試分數")
    visible_to_parent: bool = Field(default=True, description="是否對家長可見")


class ExamUpdate(BaseModel):
    exam_date: datetime | None = Field(default=None)
    exam_type: str | None = Field(default=None)
    score: float | None = Field(default=None, ge=0)
    visible_to_parent: bool | None = Field(default=None)
