from datetime import datetime

from pydantic import BaseModel, Field


class ExamCreate(BaseModel):
    student_id: int = Field(..., description="學生 ID", examples=[1])
    subject_id: int = Field(..., description="科目 ID", examples=[3])
    exam_date: datetime = Field(..., description="考試日期", examples=["2026-04-01T00:00:00"])
    exam_type: str = Field(..., description="考試類型（段考、小考、模擬考等）", examples=["段考"])
    score: float = Field(..., description="考試分數", examples=[85.5])
    visible_to_parent: bool = Field(default=True, description="是否對家長可見", examples=[True])


class ExamUpdate(BaseModel):
    exam_date: datetime | None = Field(default=None, description="考試日期", examples=["2026-04-01T00:00:00"])
    exam_type: str | None = Field(default=None, description="考試類型（段考、小考、模擬考等）", examples=["段考"])
    score: float | None = Field(default=None, description="考試分數", examples=[85.5])
    visible_to_parent: bool | None = Field(default=None, description="是否對家長可見", examples=[True])
