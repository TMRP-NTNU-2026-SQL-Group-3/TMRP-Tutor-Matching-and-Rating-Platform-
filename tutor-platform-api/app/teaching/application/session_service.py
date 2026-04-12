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


def _as_str(value) -> str:
    if value is None:
        return ""
    return str(value)


class SessionAppService:
    def __init__(self, repo: ISessionRepository, uow: IUnitOfWork):
        self._repo = repo
        self._uow = uow

    def create(self, *, tutor_user_id: int, match_id: int, **fields) -> int:
        match = self._repo.get_match_for_create(match_id)
        if not match:
            raise NotFoundError("找不到此配對")
        if match["tutor_user_id"] != tutor_user_id:
            raise PermissionDeniedError("只有此配對的老師可以新增上課日誌")
        if match["status"] not in _ACTIVE_SESSION_STATUSES:
            raise MatchNotActiveError()
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
        return self._repo.list_by_match(match_id, parent_only=is_parent and not is_tutor)

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
                if _as_str(old_val) != _as_str(new_val):
                    diffs.append((field, old_val, new_val))
            if not diffs:
                return {"session_id": session_id, "changed": False, "message": "無實際變動"}
            self._repo.update(session_id, updates)
            for field, old_val, new_val in diffs:
                self._repo.insert_edit_log(session_id, field, old_val, new_val)
        return {"session_id": session_id, "changed": True, "message": "上課日誌已更新"}

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
