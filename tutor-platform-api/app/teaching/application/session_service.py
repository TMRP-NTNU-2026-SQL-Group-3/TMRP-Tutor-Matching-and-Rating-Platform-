"""Application service for teaching-session CRUD.

Owns resource-ownership checks (is this the tutor of the match, is this user a
participant of the match) so the router only handles HTTP plumbing. Role
gating (tutor-only endpoints) remains at the router via `require_role`.
"""

from app.matching.domain.value_objects import MatchStatus
from app.shared.domain.exceptions import (
    DomainException,
    NotFoundError,
    PermissionDeniedError,
)
from app.shared.domain.ports import IUnitOfWork
from app.teaching.domain.exceptions import MatchNotActiveError, SessionNotFoundError
from app.teaching.domain.ports import ISessionRepository


_ACTIVE_SESSION_STATUSES = {MatchStatus.ACTIVE.value, MatchStatus.TRIAL.value}

# Statuses where the match never entered an active teaching relationship;
# participants of these matches have no legitimate claim to session logs.
_SESSION_UNREADABLE_STATUSES = {MatchStatus.PENDING.value, MatchStatus.REJECTED.value}

# Session fields not shown to parents (visible_to_parent gating); edit logs
# for these fields must also be withheld from parent viewers.
_PARENT_HIDDEN_FIELDS = frozenset({"student_performance", "next_plan"})


def _normalize(value):
    """Normalize a value for change detection so that equivalent values
    of different types (e.g. int 1 vs float 1.0, Decimal vs float)
    compare correctly.

    NUMERIC columns (hours) come back as Decimal from psycopg2. Routing the
    value through float would lose precision for values like 0.1 that are
    exact in Decimal but not in float, causing spurious "changed" logs.
    All numeric inputs are therefore normalized to Decimal, and integers
    collapse to a plain int for clean comparison with JSON payloads.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    from decimal import Decimal, InvalidOperation
    if isinstance(value, (int, float, Decimal)):
        try:
            d = value if isinstance(value, Decimal) else Decimal(str(value))
        except (InvalidOperation, ValueError):
            return str(value)
        as_int = int(d)
        return as_int if d == as_int else d
    return str(value)


class SessionAppService:
    def __init__(self, repo: ISessionRepository, uow: IUnitOfWork):
        self._repo = repo
        self._uow = uow

    def create(self, *, tutor_user_id: int, match_id: int, **fields) -> int:
        match = self._repo.get_match_for_create(match_id)
        if not match:
            raise NotFoundError("找不到此配對")
        # S-H2: ownership check — the service independently verifies the caller
        # is the tutor on this match, not just any authenticated tutor.
        if match["tutor_user_id"] != tutor_user_id:
            raise PermissionDeniedError("只有此配對的老師可以新增上課日誌")
        if match["status"] not in _ACTIVE_SESSION_STATUSES:
            raise MatchNotActiveError()
        return self._repo.create(match_id=match_id, **fields)

    def list_for_match(self, *, match_id: int, user_id: int, is_admin: bool) -> list[dict]:
        # ARCH-12: re-verify participant membership inside the same transaction
        # that fetches sessions. FOR SHARE prevents a concurrent participant
        # change from racing between the permission check and the data read.
        with self._uow.begin():
            match = self._repo.get_match_participants_for_share(match_id)
            if not match:
                raise NotFoundError("找不到此配對")
            is_tutor = match["tutor_user_id"] == user_id
            is_parent = match["parent_user_id"] == user_id
            if not is_tutor and not is_parent and not is_admin:
                raise PermissionDeniedError("無權查看此配對的上課日誌")
            # BAC-1: reject ex-participants of matches that were never active.
            if not is_admin and match["status"] in _SESSION_UNREADABLE_STATUSES:
                raise PermissionDeniedError("此配對狀態下無法查看上課日誌")
            # Parents only see entries the tutor flagged visible.
            return self._repo.list_by_match(match_id, visible_only=is_parent and not is_tutor)

    def update(self, *, session_id: int, tutor_user_id: int, updates: dict) -> dict:
        if not updates:
            raise DomainException("未提供任何修改欄位")
        if "visible_to_parent" in updates and updates["visible_to_parent"] is not None:
            updates["visible_to_parent"] = bool(updates["visible_to_parent"])

        with self._uow.begin():
            fresh = self._repo.get_by_id_for_update(session_id)
            if not fresh:
                raise SessionNotFoundError()
            match = self._repo.get_match_for_create(fresh["match_id"])
            if not match or match["tutor_user_id"] != tutor_user_id:
                raise PermissionDeniedError("只有此配對的老師可以修改上課日誌")
            if match["status"] not in _ACTIVE_SESSION_STATUSES:
                raise MatchNotActiveError()
            diffs = []
            for field, new_val in updates.items():
                old_val = fresh.get(field)
                if field == "visible_to_parent" and old_val is not None:
                    old_val = bool(old_val)
                if _normalize(old_val) != _normalize(new_val):
                    diffs.append((field, old_val, new_val))
            if not diffs:
                return {"session_id": session_id, "changed": False, "message": "無實際變動"}
            self._repo.update(session_id, updates)
            for field, old_val, new_val in diffs:
                self._repo.insert_edit_log(session_id, field, old_val, new_val)
        return {"session_id": session_id, "changed": True, "message": "上課日誌已更新"}

    def delete(self, *, session_id: int, tutor_user_id: int) -> None:
        with self._uow.begin():
            session = self._repo.get_by_id_for_update(session_id)
            if not session:
                raise SessionNotFoundError()
            match = self._repo.get_match_for_create(session["match_id"])
            if not match or match["tutor_user_id"] != tutor_user_id:
                raise PermissionDeniedError("只有此配對的老師可以刪除上課日誌")
            self._repo.delete(session_id)

    def get_edit_logs(self, *, session_id: int, user_id: int, is_admin: bool) -> list[dict]:
        session = self._repo.get_by_id(session_id)
        if not session:
            raise SessionNotFoundError()
        match = self._repo.get_match_participants(session["match_id"])
        if not match:
            raise NotFoundError("找不到此配對")
        is_tutor = match["tutor_user_id"] == user_id
        is_parent = match["parent_user_id"] == user_id
        if not is_tutor and not is_parent and not is_admin:
            raise PermissionDeniedError("無權查看此日誌的修改歷史")
        logs = self._repo.get_edit_logs(session_id)
        # BAC-3: parents must not see edit history of fields they cannot read.
        if is_parent and not is_tutor and not is_admin:
            logs = [lg for lg in logs if lg["field_name"] not in _PARENT_HIDDEN_FIELDS]
        return logs
