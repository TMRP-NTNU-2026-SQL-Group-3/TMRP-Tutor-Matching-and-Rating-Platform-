from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class MatchStatus(str, Enum):
    PENDING = "pending"
    TRIAL = "trial"
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    TERMINATING = "terminating"
    ENDED = "ended"

    @property
    def label(self) -> str:
        return _STATUS_LABELS[self]

    @property
    def is_terminal(self) -> bool:
        return self in (self.CANCELLED, self.REJECTED, self.ENDED)


_STATUS_LABELS = {
    MatchStatus.PENDING: "等待中",
    MatchStatus.TRIAL: "試教中",
    MatchStatus.ACTIVE: "進行中",
    MatchStatus.PAUSED: "已暫停",
    MatchStatus.CANCELLED: "已取消",
    MatchStatus.REJECTED: "已拒絕",
    MatchStatus.TERMINATING: "等待終止確認",
    MatchStatus.ENDED: "已結束",
}


class Action(str, Enum):
    CANCEL = "cancel"
    REJECT = "reject"
    ACCEPT = "accept"
    CONFIRM_TRIAL = "confirm_trial"
    REJECT_TRIAL = "reject_trial"
    PAUSE = "pause"
    RESUME = "resume"
    TERMINATE = "terminate"
    AGREE_TERMINATE = "agree_terminate"
    DISAGREE_TERMINATE = "disagree_terminate"


class AllowedActor(str, Enum):
    PARENT = "parent"
    TUTOR = "tutor"
    EITHER = "either"
    OTHER_PARTY = "other_party"


@dataclass(frozen=True)
class Contract:
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

    def __post_init__(self) -> None:
        # Invariants enforced here so a malformed Contract cannot reach the
        # state machine or DB writes — the object is supposed to represent a
        # concrete, signable agreement. Anything that would be non-sensical in
        # a real contract (negative rate, zero sessions, trial priced without
        # want_trial, end_date before start_date) is a bug upstream and must
        # surface at construction time, not as a mystery NULL downstream.
        if self.hourly_rate < 0:
            raise ValueError("hourly_rate must be >= 0")
        if self.sessions_per_week < 0:
            raise ValueError("sessions_per_week must be >= 0")
        if self.trial_price is not None and self.trial_price < 0:
            raise ValueError("trial_price must be >= 0")
        if self.trial_count is not None and self.trial_count < 0:
            raise ValueError("trial_count must be >= 0")
        if self.penalty_amount is not None and self.penalty_amount < 0:
            raise ValueError("penalty_amount must be >= 0")
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date must not precede start_date")
