from pydantic import BaseModel


class MatchCreate(BaseModel):
    tutor_id: int
    student_id: int
    subject_id: int
    hourly_rate: float
    sessions_per_week: int
    want_trial: bool = False
    invite_message: str | None = None


class MatchStatusUpdate(BaseModel):
    action: str  # accept, reject, cancel, confirm_trial, reject_trial, pause, resume, terminate, agree_terminate, disagree_terminate
    reason: str | None = None
