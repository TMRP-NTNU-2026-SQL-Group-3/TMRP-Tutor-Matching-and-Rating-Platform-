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
