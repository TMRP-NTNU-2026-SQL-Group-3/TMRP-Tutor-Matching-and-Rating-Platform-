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

        Returns the extracted status when the stored format is valid,
        otherwise raises ValueError so callers notice a data-integrity
        issue instead of silently receiving a wrong default.
        """
        raw = self.termination_reason or ""
        if "|" in raw:
            prev = raw.split("|", 1)[0]
        else:
            prev = raw
        if prev in self._VALID_PRE_TERMINATION_STATUSES:
            return prev
        if raw:
            raise ValueError(
                f"Cannot extract pre-termination status from "
                f"termination_reason '{raw}'"
            )
        return "active"

    def is_participant(self, user_id: int) -> bool:
        return user_id == self.parent_user_id or user_id == self.tutor_user_id
