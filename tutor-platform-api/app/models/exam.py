from datetime import datetime

from pydantic import BaseModel


class ExamCreate(BaseModel):
    student_id: int
    subject_id: int
    exam_date: datetime
    exam_type: str  # 段考, 小考, 模擬考, etc.
    score: float
    visible_to_parent: bool = True


class ExamUpdate(BaseModel):
    exam_date: datetime | None = None
    exam_type: str | None = None
    score: float | None = None
    visible_to_parent: bool | None = None
