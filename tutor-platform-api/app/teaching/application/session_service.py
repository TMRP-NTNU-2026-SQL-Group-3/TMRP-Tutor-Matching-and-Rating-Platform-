"""Application service for teaching-session CRUD.

Owns resource-ownership checks (is this the tutor of the match, is this user a
participant of the match) so the router only handles HTTP plumbing. Role
gating (tutor-only endpoints) remains at the router via `require_role`.
"""

from app.matching.domain.value_objects import MatchStatus
from app.middleware.rate_limit import check_and_record_bucket
from app.shared.domain.exceptions import (
    DomainException,
    NotFoundError,
    PermissionDeniedError,
    TooManyRequestsError,
)
from app.shared.domain.ports import IUnitOfWork
from app.teaching.domain.exceptions import MatchNotActiveError, SessionNotFoundError
from app.teaching.domain.ports import ISessionRepository


_ACTIVE_SESSION_STATUSES = {MatchStatus.ACTIVE.value, MatchStatus.TRIAL.value}

# B6: Path-based rate-limiting in the middleware can't distinguish "60
# session logs for one match in a minute" from "60 across 60 different
# matches". Add a per-match+tutor service-layer bucket so a misbehaving
# or runaway client can't flood a single match's log with notes.
_SESSION_CREATE_LIMIT = 10
_SESSION_CREATE_WINDOW = 60


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
        # Keyed on match+tutor so the bucket survives IP changes (mobile
        # networks, roaming) but still isolates different matches from
        # each other.
        bucket = f"session:create|match={match_id}|tutor={tutor_user_id}"
        if not check_and_record_bucket(bucket, _SESSION_CREATE_LIMIT, _SESSION_CREATE_WINDOW):
            raise TooManyRequestsError("此配對的上課日誌新增頻率過高，請稍後再試")
        return self._repo.create(match_id=match_id, **fields)

    def list_for_match(self, *, match_id: int, user_id: int, is_admin: bool) -> list[dict]:
        match = self._repo.get_match_participants(match_id)
        if not match:
            raise NotFoundError("找不到此配對")
        is_tutor = match["tutor_user_id"] == user_id
        is_parent = match["parent_user_id"] == user_id
        if not is_tutor and not is_parent and not is_admin:
            raise PermissionDeniedError("無權查看此配對的上課日誌")
        # Parents only see entries the tutor flagged visible.
        return self._repo.list_by_match(match_id, visible_only=is_parent and not is_tutor)

    def update(self, *, session_id: int, tutor_user_id: int, updates: dict) -> dict:
        session = self._repo.get_by_id(session_id)
        if not session:
            raise SessionNotFoundError()
        match = self._repo.get_match_for_create(session["match_id"])
        if not match or match["tutor_user_id"] != tutor_user_id:
            raise PermissionDeniedError("只有此配對的老師可以修改上課日誌")

        if not updates:
            raise DomainException("未提供任何修改欄位")
        if "visible_to_parent" in updates:
            if updates["visible_to_parent"] is None:
                del updates["visible_to_parent"]
            else:
                updates["visible_to_parent"] = bool(updates["visible_to_parent"])
        if not updates:
            return {"session_id": session_id, "changed": False, "message": "無需更新的欄位"}

        with self._uow.begin():
            fresh = self._repo.get_by_id(session_id)
            if not fresh:
                raise SessionNotFoundError()
            diffs = []
            for field, new_val in updates.items():
                old_val = fresh.get(field)
                if field == "visible_to_parent":
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
        session = self._repo.get_by_id(session_id)
        if not session:
            raise SessionNotFoundError()
        match = self._repo.get_match_for_create(session["match_id"])
        if not match or match["tutor_user_id"] != tutor_user_id:
            raise PermissionDeniedError("只有此配對的老師可以刪除上課日誌")
        with self._uow.begin():
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
        return self._repo.get_edit_logs(session_id)
