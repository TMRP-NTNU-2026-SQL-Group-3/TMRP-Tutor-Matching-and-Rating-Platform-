from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .value_objects import Contract, MatchStatus


@dataclass
class Match:
    match_id: int
    tutor_id: int
    student_id: int
    subject_id: int
    status: MatchStatus
    contract: Contract
    terminated_by: int | None = None
    termination_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    subject_name: str | None = None
    student_name: str | None = None
    parent_user_id: int | None = None
    tutor_user_id: int | None = None
    tutor_display_name: str | None = None

    @property
    def status_label(self) -> str:
        return self.status.label

    @property
    def parsed_termination_reason(self) -> str | None:
        if not self.termination_reason:
            return None
        if "|" in self.termination_reason:
            return self.termination_reason.split("|", 1)[1]
        return self.termination_reason

    _VALID_PRE_TERMINATION_STATUSES = {"active", "paused"}

    @property
    def previous_status_before_terminating(self) -> str:
        """Extract the status stored before termination from the
        ``{previous_status}|{reason}`` or bare ``{previous_status}``
        format (the repo omits the pipe when no reason is provided).

        Raises ValueError if the stored value is missing or unparseable —
        a match in TERMINATING status without a valid payload is a
        data-integrity bug that silently defaulting to "active" would mask.
        """
        raw = self.termination_reason or ""
        if not raw:
            raise ValueError(
                "termination_reason is empty — cannot determine "
                "pre-termination status"
            )
        prev = raw.split("|", 1)[0] if "|" in raw else raw
        if prev not in self._VALID_PRE_TERMINATION_STATUSES:
            raise ValueError(
                f"Cannot extract pre-termination status from "
                f"termination_reason '{raw}'"
            )
        return prev

    def is_direct_participant(self, user_id: int) -> bool:
        # ARCH-20: renamed from is_participant to make explicit that admins
        # are not included — callers must separately check is_admin when needed.
        return user_id == self.parent_user_id or user_id == self.tutor_user_id
