from datetime import datetime

from pydantic import BaseModel


class SessionCreate(BaseModel):
    match_id: int
    session_date: datetime
    hours: float
    content_summary: str
    homework: str | None = None
    student_performance: str | None = None
    next_plan: str | None = None
    visible_to_parent: bool = False


class SessionUpdate(BaseModel):
    session_date: datetime | None = None
    hours: float | None = None
    content_summary: str | None = None
    homework: str | None = None
    student_performance: str | None = None
    next_plan: str | None = None
    visible_to_parent: bool | None = None
