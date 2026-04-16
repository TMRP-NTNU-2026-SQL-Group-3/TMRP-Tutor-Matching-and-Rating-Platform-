from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.matching.domain.entities import Match


class MatchCreate(BaseModel):
    tutor_id: int = Field(..., description="家教 ID")
    student_id: int = Field(..., description="學生 ID")
    subject_id: int = Field(..., description="科目 ID")
    hourly_rate: float = Field(..., gt=0, description="每小時費率")
    sessions_per_week: int = Field(..., description="每週上課次數")
    want_trial: bool = Field(default=False, description="是否希望試教")
    invite_message: str | None = Field(default=None, max_length=1000, description="邀請訊息")


class MatchStatusUpdate(BaseModel):
    action: str = Field(..., description="狀態變更動作")
    reason: str | None = Field(default=None, max_length=1000, description="原因說明")
    # Spec Module D: when transitioning trial → active, both parties confirm
    # the contract terms. Optional so other actions stay unchanged.
    hourly_rate: float | None = Field(default=None, gt=0, description="正式合作時薪")
    sessions_per_week: int | None = Field(default=None, ge=1, description="正式合作每週堂數")
    start_date: datetime | None = Field(default=None, description="正式合作起始日")


class MatchDetailResponse(BaseModel):
    """Public API contract for a single match. Decoupled from the Match entity
    so renaming a domain field does not break the HTTP contract."""

    model_config = ConfigDict(from_attributes=False)

    match_id: int
    tutor_id: int
    student_id: int
    subject_id: int
    status: str
    status_label: str
    hourly_rate: float
    sessions_per_week: int
    want_trial: bool
    invite_message: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    penalty_amount: float | None = None
    trial_price: float | None = None
    trial_count: int | None = None
    contract_notes: str | None = None
    terminated_by: int | None = None
    termination_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    subject_name: str | None = None
    student_name: str | None = None
    parent_user_id: int | None = None
    tutor_user_id: int | None = None
    tutor_display_name: str | None = None
    is_parent: bool
    is_tutor: bool

    @classmethod
    def from_entity(cls, match: Match, *, is_parent: bool, is_tutor: bool) -> "MatchDetailResponse":
        c = match.contract
        return cls(
            match_id=match.match_id,
            tutor_id=match.tutor_id,
            student_id=match.student_id,
            subject_id=match.subject_id,
            status=match.status.value,
            status_label=match.status_label,
            hourly_rate=c.hourly_rate,
            sessions_per_week=c.sessions_per_week,
            want_trial=c.want_trial,
            invite_message=c.invite_message,
            start_date=c.start_date,
            end_date=c.end_date,
            penalty_amount=c.penalty_amount,
            trial_price=c.trial_price,
            trial_count=c.trial_count,
            contract_notes=c.contract_notes,
            terminated_by=match.terminated_by,
            termination_reason=match.parsed_termination_reason,
            created_at=match.created_at,
            updated_at=match.updated_at,
            subject_name=match.subject_name,
            student_name=match.student_name,
            parent_user_id=match.parent_user_id,
            tutor_user_id=match.tutor_user_id,
            tutor_display_name=match.tutor_display_name,
            is_parent=is_parent,
            is_tutor=is_tutor,
        )
