"""Unit tests for the matching state machine (pure domain logic, no DB).

Covers the transition table in app.matching.domain.state_machine, including
actor-permission enforcement and the two status-deriving edges where the
resulting status depends on runtime inputs (ACCEPT respects want_trial;
DISAGREE_TERMINATE reverts rather than choosing a fixed next state).
"""

import pytest

from app.matching.domain.exceptions import (
    InvalidTransitionError,
    MatchPermissionDeniedError,
)
from app.matching.domain.state_machine import resolve_transition
from app.matching.domain.value_objects import Action, MatchStatus


def _call(current, action, **overrides):
    defaults = dict(
        actor_is_parent=False,
        actor_is_tutor=False,
        actor_is_admin=False,
        actor_user_id=1,
        terminated_by=None,
        want_trial=False,
    )
    defaults.update(overrides)
    return resolve_transition(current, action, **defaults)


class TestHappyPathTransitions:
    def test_parent_cancels_pending(self):
        assert _call(MatchStatus.PENDING, Action.CANCEL, actor_is_parent=True) == MatchStatus.CANCELLED

    def test_tutor_rejects_pending(self):
        assert _call(MatchStatus.PENDING, Action.REJECT, actor_is_tutor=True) == MatchStatus.REJECTED

    def test_tutor_accept_without_trial_goes_active(self):
        assert _call(MatchStatus.PENDING, Action.ACCEPT, actor_is_tutor=True, want_trial=False) == MatchStatus.ACTIVE

    def test_tutor_accept_with_trial_goes_trial(self):
        assert _call(MatchStatus.PENDING, Action.ACCEPT, actor_is_tutor=True, want_trial=True) == MatchStatus.TRIAL

    def test_confirm_trial_goes_active(self):
        assert _call(MatchStatus.TRIAL, Action.CONFIRM_TRIAL, actor_is_parent=True) == MatchStatus.ACTIVE

    def test_pause_active(self):
        assert _call(MatchStatus.ACTIVE, Action.PAUSE, actor_is_tutor=True) == MatchStatus.PAUSED

    def test_resume_paused(self):
        assert _call(MatchStatus.PAUSED, Action.RESUME, actor_is_parent=True) == MatchStatus.ACTIVE

    def test_terminate_active_goes_terminating(self):
        assert _call(MatchStatus.ACTIVE, Action.TERMINATE, actor_is_parent=True) == MatchStatus.TERMINATING

    def test_other_party_agrees_termination(self):
        # Tutor started termination (terminated_by=2); parent (user_id=1) must agree.
        assert _call(
            MatchStatus.TERMINATING, Action.AGREE_TERMINATE,
            actor_is_parent=True, actor_user_id=1, terminated_by=2,
        ) == MatchStatus.ENDED


class TestInvalidTransitions:
    def test_cannot_cancel_from_active(self):
        with pytest.raises(InvalidTransitionError):
            _call(MatchStatus.ACTIVE, Action.CANCEL, actor_is_parent=True)

    def test_cannot_accept_active(self):
        with pytest.raises(InvalidTransitionError):
            _call(MatchStatus.ACTIVE, Action.ACCEPT, actor_is_tutor=True)

    def test_cannot_resume_from_ended(self):
        with pytest.raises(InvalidTransitionError):
            _call(MatchStatus.ENDED, Action.RESUME, actor_is_parent=True)


class TestActorPermissions:
    def test_tutor_cannot_cancel_pending(self):
        # CANCEL is PARENT-only.
        with pytest.raises(MatchPermissionDeniedError):
            _call(MatchStatus.PENDING, Action.CANCEL, actor_is_tutor=True)

    def test_parent_cannot_reject_pending(self):
        # REJECT is TUTOR-only.
        with pytest.raises(MatchPermissionDeniedError):
            _call(MatchStatus.PENDING, Action.REJECT, actor_is_parent=True)

    def test_outsider_cannot_pause(self):
        # EITHER requires parent/tutor/admin; an unrelated user must be rejected.
        with pytest.raises(MatchPermissionDeniedError):
            _call(MatchStatus.ACTIVE, Action.PAUSE)

    def test_initiator_cannot_confirm_own_termination(self):
        # OTHER_PARTY: whoever started termination cannot also resolve it.
        with pytest.raises(MatchPermissionDeniedError):
            _call(
                MatchStatus.TERMINATING, Action.AGREE_TERMINATE,
                actor_is_tutor=True, actor_user_id=2, terminated_by=2,
            )

    def test_admin_bypass_does_not_apply_to_other_party(self):
        # Admins are explicitly excluded from the OTHER_PARTY short-circuit: a
        # termination still needs confirmation from the non-initiating side.
        with pytest.raises(MatchPermissionDeniedError):
            _call(
                MatchStatus.TERMINATING, Action.AGREE_TERMINATE,
                actor_is_admin=True, actor_user_id=2, terminated_by=2,
            )

    def test_admin_can_cancel_pending(self):
        # For non-OTHER_PARTY transitions admins bypass actor role checks.
        assert _call(
            MatchStatus.PENDING, Action.CANCEL,
            actor_is_admin=True,
        ) == MatchStatus.CANCELLED


class TestDisagreeTermination:
    def test_disagree_returns_none_sentinel(self):
        # None signals "clear terminated_by; revert to pre-TERMINATING state".
        # The caller (MatchAppService) is responsible for choosing ACTIVE/PAUSED.
        result = _call(
            MatchStatus.TERMINATING, Action.DISAGREE_TERMINATE,
            actor_is_parent=True, actor_user_id=1, terminated_by=2,
        )
        assert result is None

    def test_initiator_cannot_disagree_own_termination(self):
        with pytest.raises(MatchPermissionDeniedError):
            _call(
                MatchStatus.TERMINATING, Action.DISAGREE_TERMINATE,
                actor_is_parent=True, actor_user_id=1, terminated_by=1,
            )
