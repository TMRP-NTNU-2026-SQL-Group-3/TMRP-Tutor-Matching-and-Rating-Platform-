import logging
from dataclasses import dataclass

from app.matching.domain import state_machine
from app.matching.domain.entities import Match
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
from app.matching.domain.ports import ICatalogQuery, IMatchRepository, IUnitOfWork
from app.matching.domain.value_objects import Action, MatchStatus

logger = logging.getLogger(__name__)


@dataclass
class MatchDetailView:
    """Application-layer view of a match for a specific viewer. Carries the
    domain entity plus viewer-scoped flags; the API layer maps to a DTO."""

    match: Match
    is_parent: bool
    is_tutor: bool


class MatchAppService:
    def __init__(
        self,
        match_repo: IMatchRepository,
        catalog: ICatalogQuery,
        uow: IUnitOfWork,
    ):
        self._match_repo = match_repo
        self._catalog = catalog
        self._uow = uow

    def create_match(
        self, *, user_id: int, tutor_id: int, student_id: int,
        subject_id: int, hourly_rate: float, sessions_per_week: int,
        want_trial: bool, invite_message: str | None,
    ) -> int:
        with self._uow.begin():
            # All consistency checks live inside the tx. The student row is locked
            # FOR UPDATE so a concurrent transfer/delete cannot slip between the
            # ownership check and the INSERT below.
            owner = self._catalog.get_student_owner_for_update(student_id)
            if owner != user_id:
                raise StudentNotOwnedError()

            # Lock the tutor row for the rest of the tx: the capacity read
            # below must not race with a sibling create_match for the same
            # tutor that also sees (active < max_students).
            if not self._catalog.lock_tutor_for_update(tutor_id):
                raise TutorNotFoundError()

            if not self._catalog.tutor_teaches_subject(tutor_id, subject_id):
                raise SubjectNotTaughtError()

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

    def get_detail(self, *, match_id: int, user_id: int, is_admin: bool) -> MatchDetailView:
        match = self._match_repo.find_by_id(match_id)
        if match is None:
            raise MatchNotFoundError()

        is_parent = match.parent_user_id == user_id
        is_tutor = match.tutor_user_id == user_id
        if not is_parent and not is_tutor and not is_admin:
            raise MatchPermissionDeniedError("無權查看此配對")

        return MatchDetailView(match=match, is_parent=is_parent, is_tutor=is_tutor)

    def update_status(
        self, *, match_id: int, action_str: str, reason: str | None,
        user_id: int, is_admin: bool,
        contract_terms: dict | None = None,
    ) -> dict:
        match = self._match_repo.find_by_id(match_id)
        if match is None:
            raise MatchNotFoundError()

        is_parent = match.parent_user_id == user_id
        is_tutor = match.tutor_user_id == user_id
        if not is_parent and not is_tutor and not is_admin:
            raise MatchPermissionDeniedError("無權操作此配對")

        action = Action(action_str)
        old_status = match.status

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
            with self._uow.begin():
                self._match_repo.set_terminating(
                    match_id, user_id, reason, match.status.value
                )
                self._audit_admin_transition(
                    match_id, user_id, is_admin, action,
                    old_status.value, MatchStatus.TERMINATING.value, reason,
                )
            new_status = MatchStatus.TERMINATING

        elif action == Action.DISAGREE_TERMINATE:
            with self._uow.begin():
                fresh = self._match_repo.find_by_id(match_id)
                if not fresh or fresh.status != MatchStatus.TERMINATING:
                    raise InvalidTransitionError("配對狀態已變更，請重新整理頁面")
                prev = fresh.previous_status_before_terminating
                self._match_repo.clear_termination(match_id, prev)
                new_status = MatchStatus(prev)
                self._audit_admin_transition(
                    match_id, user_id, is_admin, action,
                    old_status.value, new_status.value, reason,
                )
        elif action == Action.CONFIRM_TRIAL:
            # Spec Module D: trial → active is the parties' formal contract
            # confirmation, so persist any edited terms in the same tx as the
            # status flip. Trial slots do not count against the tutor's active
            # roster, so a tutor at max_students could confirm multiple trials
            # and overflow the cap; re-check capacity here under the same lock
            # pattern as create_match / resume.
            has_terms = self._has_contract_terms(contract_terms)
            with self._uow.begin():
                if new_status == MatchStatus.ACTIVE:
                    if not self._catalog.lock_tutor_for_update(match.tutor_id):
                        raise TutorNotFoundError()
                    active = self._catalog.get_active_student_count(match.tutor_id)
                    max_s = self._catalog.get_max_students(match.tutor_id)
                    if active >= max_s:
                        raise CapacityExceededError()
                if has_terms:
                    self._match_repo.confirm_trial_with_terms(
                        match_id=match_id,
                        new_status=new_status.value,
                        hourly_rate=contract_terms.get("hourly_rate"),
                        sessions_per_week=contract_terms.get("sessions_per_week"),
                        start_date=contract_terms.get("start_date"),
                    )
                else:
                    self._match_repo.update_status(match_id, new_status.value)
                self._audit_admin_transition(
                    match_id, user_id, is_admin, action,
                    old_status.value, new_status.value, reason,
                )
        elif action == Action.RESUME:
            # B1: paused → active re-enters the tutor's active roster. Without
            # re-checking capacity here, a tutor at max_students could pause
            # one match and have a second resume concurrently, exceeding the
            # cap. Mirror the create_match gate: lock the tutor row, then
            # read-and-compare under the same tx that flips the status.
            with self._uow.begin():
                if not self._catalog.lock_tutor_for_update(match.tutor_id):
                    raise TutorNotFoundError()
                active = self._catalog.get_active_student_count(match.tutor_id)
                max_s = self._catalog.get_max_students(match.tutor_id)
                if active >= max_s:
                    raise CapacityExceededError()
                self._match_repo.update_status(match_id, new_status.value)
                self._audit_admin_transition(
                    match_id, user_id, is_admin, action,
                    old_status.value, new_status.value, reason,
                )
        else:
            with self._uow.begin():
                self._match_repo.update_status(match_id, new_status.value)
                self._audit_admin_transition(
                    match_id, user_id, is_admin, action,
                    old_status.value, new_status.value, reason,
                )

        return {
            "match_id": match_id,
            "new_status": new_status.value,
            "status_label": new_status.label,
        }

    def _audit_admin_transition(
        self, match_id: int, user_id: int, is_admin: bool,
        action: Action, old_status: str, new_status: str,
        reason: str | None,
    ) -> None:
        """B10: record admin-initiated match state changes to audit_log.

        Only runs when the caller holds admin role: regular tutor/parent
        transitions already leave a trace on the match row itself
        (`terminated_by`, `updated_at`, contract fields) and are out of scope
        for this audit table. Called inside the same UoW as the status write
        so the two rows commit or roll back together."""
        if not is_admin:
            return
        self._match_repo.record_admin_transition(
            match_id=match_id,
            actor_user_id=user_id,
            action=action.value,
            old_status=old_status,
            new_status=new_status,
            reason=reason,
        )

    @staticmethod
    def _has_contract_terms(terms: dict | None) -> bool:
        if not terms:
            return False
        return any(terms.get(k) is not None for k in ("hourly_rate", "sessions_per_week", "start_date"))
