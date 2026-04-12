import logging

from app.matching.domain import state_machine
from app.matching.domain.exceptions import (
    CapacityExceededError,
    DuplicateMatchError,
    InvalidTransitionError,
    MatchNotFoundError,
    MatchPermissionDeniedError,
    StudentNotOwnedError,
    SubjectNotTaughtError,
    TutorNotFoundError,
)
from app.matching.domain.ports import ICatalogQuery, IMatchRepository
from app.matching.domain.value_objects import Action, MatchStatus
from app.shared.infrastructure.database_tx import transaction

logger = logging.getLogger(__name__)


class MatchAppService:
    def __init__(self, match_repo: IMatchRepository, catalog: ICatalogQuery, conn):
        self._match_repo = match_repo
        self._catalog = catalog
        self._conn = conn

    def create_match(
        self, *, user_id: int, tutor_id: int, student_id: int,
        subject_id: int, hourly_rate: float, sessions_per_week: int,
        want_trial: bool, invite_message: str | None,
    ) -> int:
        owner = self._catalog.get_student_owner(student_id)
        if owner != user_id:
            raise StudentNotOwnedError()

        if not self._catalog.tutor_exists(tutor_id):
            raise TutorNotFoundError()

        if not self._catalog.tutor_teaches_subject(tutor_id, subject_id):
            raise SubjectNotTaughtError()

        with transaction(self._conn):
            if self._match_repo.check_duplicate_active(tutor_id, student_id, subject_id):
                raise DuplicateMatchError()

            active = self._catalog.get_active_student_count(tutor_id)
            max_s = self._catalog.get_max_students(tutor_id)
            if active >= max_s:
                raise CapacityExceededError()

            return self._match_repo.create(
                tutor_id=tutor_id, student_id=student_id,
                subject_id=subject_id, hourly_rate=hourly_rate,
                sessions_per_week=sessions_per_week,
                want_trial=want_trial, invite_message=invite_message,
            )

    def list_matches(self, *, user_id: int, role: str) -> list[dict]:
        if role == "tutor":
            matches = self._match_repo.find_by_tutor_user_id(user_id)
        elif role == "admin":
            matches = self._match_repo.find_all()
        else:
            matches = self._match_repo.find_by_parent_user_id(user_id)

        for m in matches:
            m["status_label"] = MatchStatus(m["status"]).label
        return matches

    def get_detail(self, *, match_id: int, user_id: int, is_admin: bool) -> dict:
        match = self._match_repo.find_by_id(match_id)
        if match is None:
            raise MatchNotFoundError()

        is_parent = match.parent_user_id == user_id
        is_tutor = match.tutor_user_id == user_id
        if not is_parent and not is_tutor and not is_admin:
            raise MatchPermissionDeniedError("無權查看此配對")

        # Build response dict from Match entity — 保留所有 m.* 欄位以維持 API 相容性
        data = {
            "match_id": match.match_id,
            "tutor_id": match.tutor_id,
            "student_id": match.student_id,
            "subject_id": match.subject_id,
            "status": match.status.value,
            "status_label": match.status_label,
            "hourly_rate": match.contract.hourly_rate,
            "sessions_per_week": match.contract.sessions_per_week,
            "want_trial": match.contract.want_trial,
            "invite_message": match.contract.invite_message,
            "start_date": match.contract.start_date,
            "end_date": match.contract.end_date,
            "penalty_amount": match.contract.penalty_amount,
            "trial_price": match.contract.trial_price,
            "trial_count": match.contract.trial_count,
            "contract_notes": match.contract.contract_notes,
            "terminated_by": match.terminated_by,
            "termination_reason": match.parsed_termination_reason,
            "created_at": match.created_at,
            "updated_at": match.updated_at,
            "subject_name": match.subject_name,
            "student_name": match.student_name,
            "parent_user_id": match.parent_user_id,
            "tutor_user_id": match.tutor_user_id,
            "tutor_display_name": match.tutor_display_name,
            "is_parent": is_parent,
            "is_tutor": is_tutor,
        }
        return data

    def update_status(
        self, *, match_id: int, action_str: str, reason: str | None,
        user_id: int, is_admin: bool,
    ) -> dict:
        match = self._match_repo.find_by_id(match_id)
        if match is None:
            raise MatchNotFoundError()

        is_parent = match.parent_user_id == user_id
        is_tutor = match.tutor_user_id == user_id
        if not is_parent and not is_tutor and not is_admin:
            raise MatchPermissionDeniedError("無權操作此配對")

        action = Action(action_str)

        new_status = state_machine.resolve_transition(
            current=match.status,
            action=action,
            actor_is_parent=is_parent,
            actor_is_tutor=is_tutor,
            actor_is_admin=is_admin,
            actor_user_id=user_id,
            terminated_by=match.terminated_by,
            want_trial=match.contract.want_trial,
        )

        if action == Action.TERMINATE:
            if not reason:
                raise InvalidTransitionError("終止配對需要提供原因")
            self._match_repo.set_terminating(
                match_id, user_id, reason, match.status.value
            )
            new_status = MatchStatus.TERMINATING

        elif action == Action.DISAGREE_TERMINATE:
            with transaction(self._conn):
                fresh = self._match_repo.find_by_id(match_id)
                if not fresh or fresh.status != MatchStatus.TERMINATING:
                    raise InvalidTransitionError("配對狀態已變更，請重新整理頁面")
                prev = fresh.previous_status_before_terminating
                self._match_repo.clear_termination(match_id, prev)
                new_status = MatchStatus(prev)
        else:
            self._match_repo.update_status(match_id, new_status.value)

        return {
            "match_id": match_id,
            "new_status": new_status.value,
            "status_label": new_status.label,
        }
