from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    match_id: int = Field(..., description="配對 ID", examples=[1])
    session_date: datetime = Field(..., description="上課日期時間", examples=["2026-04-05T14:00:00"])
    hours: float = Field(..., description="上課時數", examples=[2.0])
    content_summary: str = Field(..., description="上課內容摘要", examples=["複習二次函數與不等式"])
    homework: str | None = Field(default=None, description="指派作業", examples=["課本 p.50-55 習題"])
    student_performance: str | None = Field(default=None, description="學生表現紀錄", examples=["理解力佳，但計算偶有粗心"])
    next_plan: str | None = Field(default=None, description="下次上課計畫", examples=["進入三角函數單元"])
    visible_to_parent: bool = Field(default=False, description="是否對家長可見", examples=[False])


class SessionUpdate(BaseModel):
    session_date: datetime | None = Field(default=None, description="上課日期時間", examples=["2026-04-05T14:00:00"])
    hours: float | None = Field(default=None, description="上課時數", examples=[2.0])
    content_summary: str | None = Field(default=None, description="上課內容摘要", examples=["複習二次函數與不等式"])
    homework: str | None = Field(default=None, description="指派作業", examples=["課本 p.50-55 習題"])
    student_performance: str | None = Field(default=None, description="學生表現紀錄", examples=["理解力佳，但計算偶有粗心"])
    next_plan: str | None = Field(default=None, description="下次上課計畫", examples=["進入三角函數單元"])
    visible_to_parent: bool | None = Field(default=None, description="是否對家長可見", examples=[True])
