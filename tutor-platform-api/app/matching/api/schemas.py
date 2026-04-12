from pydantic import BaseModel, Field


class MatchCreate(BaseModel):
    tutor_id: int = Field(..., description="家教 ID")
    student_id: int = Field(..., description="學生 ID")
    subject_id: int = Field(..., description="科目 ID")
    hourly_rate: float = Field(..., gt=0, description="每小時費率")
    sessions_per_week: int = Field(..., description="每週上課次數")
    want_trial: bool = Field(default=False, description="是否希望試教")
    invite_message: str | None = Field(default=None, description="邀請訊息")


class MatchStatusUpdate(BaseModel):
    action: str = Field(..., description="狀態變更動作")
    reason: str | None = Field(default=None, description="原因說明")
