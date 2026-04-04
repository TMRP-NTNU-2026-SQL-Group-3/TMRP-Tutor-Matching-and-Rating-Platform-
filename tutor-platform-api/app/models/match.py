from pydantic import BaseModel, Field


class MatchCreate(BaseModel):
    tutor_id: int = Field(..., description="家教 ID", examples=[1])
    student_id: int = Field(..., description="學生 ID", examples=[2])
    subject_id: int = Field(..., description="科目 ID", examples=[3])
    hourly_rate: float = Field(..., description="每小時費率（新台幣）", examples=[600.0])
    sessions_per_week: int = Field(..., description="每週上課次數", examples=[2])
    want_trial: bool = Field(default=False, description="是否希望試教", examples=[False])
    invite_message: str | None = Field(default=None, description="邀請訊息", examples=["希望能幫孩子加強數學"])


class MatchStatusUpdate(BaseModel):
    action: str = Field(..., description="狀態變更動作（accept, reject, cancel, confirm_trial, reject_trial, pause, resume, terminate, agree_terminate, disagree_terminate）", examples=["accept"])
    reason: str | None = Field(default=None, description="原因說明", examples=["時間無法配合"])
