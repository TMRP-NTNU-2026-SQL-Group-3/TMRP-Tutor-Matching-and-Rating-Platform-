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
from app.matching.domain.value_objects import Action, Contract, MatchStatus
from app.shared.api.constants import MAX_PAGE_SIZE

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

    def list_matches(self, *, user_id: int, role: str, page: int = 1, page_size: int = 20) -> dict:
        page_size = min(page_size, MAX_PAGE_SIZE)
        limit = page_size
        offset = (page - 1) * page_size
        if role == "tutor":
            matches = self._match_repo.find_by_tutor_user_id(user_id, limit=limit, offset=offset)
            total = self._match_repo.count_by_tutor_user_id(user_id)
        elif role == "admin":
            matches = self._match_repo.find_all(limit=limit, offset=offset)
            total = self._match_repo.count_all()
        else:
            matches = self._match_repo.find_by_parent_user_id(user_id, limit=limit, offset=offset)
            total = self._match_repo.count_by_parent_user_id(user_id)

        for m in matches:
            m["status_label"] = MatchStatus(m["status"]).label

        total_pages = max(1, (total + page_size - 1) // page_size)
        return {
            "items": matches,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }

    def get_detail(self, *, match_id: int, user_id: int, is_admin: bool) -> MatchDetailView:
        # ARCH-2: read without FOR UPDATE — terminated_by and other concurrent
        # fields are eventual-consistent. Any subsequent mutation must re-fetch
        # inside a locked transaction (update_status does this via
        # find_by_id_for_update). Callers must not treat the returned view as
        # authoritative state for write decisions.
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

        try:
            action = Action(action_str)
        except ValueError:
            valid = [a.value for a in Action]
            raise InvalidTransitionError(
                f"無效的操作「{action_str}」，可用操作為：{', '.join(valid)}"
            )
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

        # ARCH-3: audit calls are intentionally placed *after* each
        # with-block. A failed audit INSERT inside an open transaction puts
        # the PostgreSQL connection into an error state, causing the entire
        # transaction (including the state change) to roll back silently.
        # Running the audit as a separate auto-committed statement ensures
        # the state change is durable before the audit is attempted.
        # _audit_admin_transition wraps the DB write in try/except so an
        # audit failure surfaces as a logged warning, not an unhandled 500.

        if action == Action.TERMINATE:
            if not reason:
                raise InvalidTransitionError("終止配對需要提供原因")
            with self._uow.begin():
                fresh = self._match_repo.find_by_id_for_update(match_id)
                if fresh is None:
                    raise MatchNotFoundError()
                is_parent = fresh.parent_user_id == user_id
                is_tutor = fresh.tutor_user_id == user_id
                if not is_parent and not is_tutor and not is_admin:
                    raise MatchPermissionDeniedError("無權操作此配對")
                locked_old_status = fresh.status.value
                state_machine.resolve_transition(
                    current=fresh.status,
                    action=action,
                    actor_is_parent=is_parent,
                    actor_is_tutor=is_tutor,
                    actor_is_admin=is_admin,
                    actor_user_id=user_id,
                    terminated_by=fresh.terminated_by,
                    want_trial=fresh.contract.want_trial,
                )
                self._match_repo.set_terminating(
                    match_id, user_id, reason, fresh.status.value
                )
            new_status = MatchStatus.TERMINATING
            self._audit_admin_transition(
                match_id, user_id, is_admin, action,
                locked_old_status, MatchStatus.TERMINATING.value, reason,
            )

        elif action == Action.DISAGREE_TERMINATE:
            with self._uow.begin():
                fresh = self._match_repo.find_by_id_for_update(match_id)
                if not fresh or fresh.status != MatchStatus.TERMINATING:
                    raise InvalidTransitionError("配對狀態已變更，請重新整理頁面")
                is_parent = fresh.parent_user_id == user_id
                is_tutor = fresh.tutor_user_id == user_id
                if not is_parent and not is_tutor and not is_admin:
                    raise MatchPermissionDeniedError("無權操作此配對")
                locked_old_status = fresh.status.value
                # ERR-1: previous_status_before_terminating raises ValueError for
                # a malformed termination_reason (e.g. imported via CSV). Catch
                # and surface as a domain error so the caller gets a 422, not a 500.
                try:
                    prev = fresh.previous_status_before_terminating
                except ValueError as exc:
                    logger.error(
                        "match_id=%s has malformed termination_reason; "
                        "DISAGREE_TERMINATE cannot recover previous status: %s",
                        match_id, exc,
                    )
                    raise InvalidTransitionError(
                        "配對的終止記錄格式異常，無法復原狀態，請聯繫管理員"
                    ) from exc
                self._match_repo.clear_termination(match_id, prev)
                new_status = MatchStatus(prev)
            self._audit_admin_transition(
                match_id, user_id, is_admin, action,
                locked_old_status, new_status.value, reason,
            )

        elif action == Action.CONFIRM_TRIAL:
            # Spec Module D: trial → active is the parties' formal contract
            # confirmation, so persist any edited terms in the same tx as the
            # status flip. Trial slots do not count against the tutor's active
            # roster, so a tutor at max_students could confirm multiple trials
            # and overflow the cap; re-check capacity here under the same lock
            # pattern as create_match / resume.
            has_terms = self._has_contract_terms(contract_terms)
            # ARCH-4: validate contract terms before opening the transaction so
            # a malformed payload raises immediately rather than rolling back
            # after the lock has already been acquired.
            new_rate = new_spw = new_start = None
            if has_terms:
                new_rate = contract_terms.get("hourly_rate")
                new_spw = contract_terms.get("sessions_per_week")
                new_start = contract_terms.get("start_date")
                try:
                    Contract(
                        hourly_rate=float(new_rate) if new_rate is not None else match.contract.hourly_rate,
                        sessions_per_week=int(new_spw) if new_spw is not None else match.contract.sessions_per_week,
                        want_trial=match.contract.want_trial,
                        start_date=new_start if new_start is not None else match.contract.start_date,
                        end_date=match.contract.end_date,
                    )
                except ValueError as exc:
                    raise InvalidTransitionError(str(exc)) from exc
            with self._uow.begin():
                fresh = self._match_repo.find_by_id_for_update(match_id)
                if fresh is None:
                    raise MatchNotFoundError()
                is_parent = fresh.parent_user_id == user_id
                is_tutor = fresh.tutor_user_id == user_id
                if not is_parent and not is_tutor and not is_admin:
                    raise MatchPermissionDeniedError("無權操作此配對")
                locked_old_status = fresh.status.value
                new_status = state_machine.resolve_transition(
                    current=fresh.status,
                    action=action,
                    actor_is_parent=is_parent,
                    actor_is_tutor=is_tutor,
                    actor_is_admin=is_admin,
                    actor_user_id=user_id,
                    terminated_by=fresh.terminated_by,
                    want_trial=fresh.contract.want_trial,
                )
                if new_status == MatchStatus.ACTIVE:
                    if not self._catalog.lock_tutor_for_update(fresh.tutor_id):
                        raise TutorNotFoundError()
                    active = self._catalog.get_active_student_count(fresh.tutor_id)
                    max_s = self._catalog.get_max_students(fresh.tutor_id)
                    if active >= max_s:
                        raise CapacityExceededError()
                if has_terms:
                    self._match_repo.confirm_trial_with_terms(
                        match_id=match_id,
                        new_status=new_status.value,
                        hourly_rate=new_rate,
                        sessions_per_week=new_spw,
                        start_date=new_start,
                    )
                else:
                    self._match_repo.update_status(match_id, new_status.value)
            self._audit_admin_transition(
                match_id, user_id, is_admin, action,
                locked_old_status, new_status.value, reason,
            )

        elif action == Action.RESUME:
            # B1: paused → active re-enters the tutor's active roster. Without
            # re-checking capacity here, a tutor at max_students could pause
            # one match and have a second resume concurrently, exceeding the
            # cap. Mirror the create_match gate: lock the tutor row, then
            # read-and-compare under the same tx that flips the status.
            with self._uow.begin():
                fresh = self._match_repo.find_by_id_for_update(match_id)
                if fresh is None:
                    raise MatchNotFoundError()
                is_parent = fresh.parent_user_id == user_id
                is_tutor = fresh.tutor_user_id == user_id
                if not is_parent and not is_tutor and not is_admin:
                    raise MatchPermissionDeniedError("無權操作此配對")
                locked_old_status = fresh.status.value
                new_status = state_machine.resolve_transition(
                    current=fresh.status,
                    action=action,
                    actor_is_parent=is_parent,
                    actor_is_tutor=is_tutor,
                    actor_is_admin=is_admin,
                    actor_user_id=user_id,
                    terminated_by=fresh.terminated_by,
                    want_trial=fresh.contract.want_trial,
                )
                if not self._catalog.lock_tutor_for_update(fresh.tutor_id):
                    raise TutorNotFoundError()
                active = self._catalog.get_active_student_count(fresh.tutor_id)
                max_s = self._catalog.get_max_students(fresh.tutor_id)
                if active >= max_s:
                    raise CapacityExceededError()
                self._match_repo.update_status(match_id, new_status.value)
            self._audit_admin_transition(
                match_id, user_id, is_admin, action,
                locked_old_status, new_status.value, reason,
            )

        else:
            locked_old_status: str = old_status.value
            with self._uow.begin():
                # Lock the match row so concurrent state changes (e.g. a
                # simultaneous ACCEPT that flips want_trial → TRIAL vs ACTIVE)
                # are serialised. Recompute new_status from the locked row so
                # the transition always reflects committed data.
                fresh = self._match_repo.find_by_id_for_update(match_id)
                if fresh is None:
                    raise MatchNotFoundError()
                is_parent = fresh.parent_user_id == user_id
                is_tutor = fresh.tutor_user_id == user_id
                if not is_parent and not is_tutor and not is_admin:
                    raise MatchPermissionDeniedError("無權操作此配對")
                locked_old_status = fresh.status.value
                new_status = state_machine.resolve_transition(
                    current=fresh.status,
                    action=action,
                    actor_is_parent=is_parent,
                    actor_is_tutor=is_tutor,
                    actor_is_admin=is_admin,
                    actor_user_id=user_id,
                    terminated_by=fresh.terminated_by,
                    want_trial=fresh.contract.want_trial,
                )
                # ARCH-1: any path that lands on ACTIVE must re-check capacity
                # under the same tutor lock used by create_match and resume.
                # Without this, two concurrent ACCEPT requests (want_trial=False)
                # can both read (active < max_students) before either commits,
                # leaving the tutor over-enrolled.
                if new_status == MatchStatus.ACTIVE:
                    if not self._catalog.lock_tutor_for_update(fresh.tutor_id):
                        raise TutorNotFoundError()
                    active = self._catalog.get_active_student_count(fresh.tutor_id)
                    max_s = self._catalog.get_max_students(fresh.tutor_id)
                    if active >= max_s:
                        raise CapacityExceededError()
                self._match_repo.update_status(match_id, new_status.value)
            self._audit_admin_transition(
                match_id, user_id, is_admin, action,
                locked_old_status, new_status.value, reason,
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

        Scope: admin callers only. Tutor/parent transitions are intentionally
        excluded from audit_log — their changes are traceable via the match row
        itself (terminated_by, updated_at, contract fields). If a persistent
        participant audit stream is needed in future, add a separate table and
        call site rather than expanding this method (SEC-14).

        For non-admin callers, transitions are logged at INFO level to the
        application log so they remain observable without polluting audit_log."""
        if not is_admin:
            logger.info(
                "match_transition match_id=%s user_id=%s action=%s %s→%s reason=%r",
                match_id, user_id, action.value, old_status, new_status, reason,
            )
            return
        # ARCH-3: audit failure must not roll back the state transition.
        # Wrap the INSERT so a transient constraint error or schema mismatch
        # surfaces as a logged warning rather than silently undoing the commit.
        try:
            self._match_repo.record_admin_transition(
                match_id=match_id,
                actor_user_id=user_id,
                action=action.value,
                old_status=old_status,
                new_status=new_status,
                reason=reason,
            )
        except Exception:
            logger.exception(
                "audit_log write failed for match_id=%s action=%s %s→%s — "
                "state change was committed but audit row is missing",
                match_id, action.value, old_status, new_status,
            )

    @staticmethod
    def _has_contract_terms(terms: dict | None) -> bool:
        if not terms:
            return False
        return any(terms.get(k) is not None for k in ("hourly_rate", "sessions_per_week", "start_date"))
