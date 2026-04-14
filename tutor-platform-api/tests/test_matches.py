"""Match state-machine tests: create, 8 legal transitions, illegal transitions,
permission checks.

Patches the Matching BC infrastructure dependencies at their import sites
inside `app.matching.api.router`:
    - PostgresMatchRepository → the match repo
    - CatalogQueryAdapter → tutor/student/capacity lookups
Uses the real `PostgresUnitOfWork` wrapping the MagicMock connection; the
shared `transaction()` helper treats a MagicMock as already-in-transaction
and becomes a no-op, so we never need to stub out the UoW itself.
"""

from unittest.mock import patch

from app.matching.domain.entities import Match
from app.matching.domain.value_objects import Contract, MatchStatus


_MATCH_REPO_PATH = "app.matching.api.router.PostgresMatchRepository"
_CATALOG_PATH = "app.matching.api.router.CatalogQueryAdapter"


def _match_entity(**overrides) -> Match:
    """Build a Match entity for testing. parent=user 1, tutor=user 2 by default."""
    defaults = {
        "match_id": 1,
        "tutor_id": 1,
        "student_id": 1,
        "subject_id": 1,
        "status": MatchStatus.PENDING,
        "terminated_by": None,
        "termination_reason": None,
        "subject_name": "數學",
        "student_name": "小明",
        "parent_user_id": 1,
        "tutor_user_id": 2,
        "tutor_display_name": "陳老師",
    }
    contract_overrides = {}
    for key in ("hourly_rate", "sessions_per_week", "want_trial",
                "invite_message", "start_date", "end_date",
                "penalty_amount", "trial_price", "trial_count",
                "contract_notes"):
        if key in overrides:
            contract_overrides[key] = overrides.pop(key)
    contract = Contract(
        hourly_rate=contract_overrides.get("hourly_rate", 600),
        sessions_per_week=contract_overrides.get("sessions_per_week", 2),
        want_trial=contract_overrides.get("want_trial", False),
        invite_message=contract_overrides.get("invite_message"),
        start_date=contract_overrides.get("start_date"),
        end_date=contract_overrides.get("end_date"),
        penalty_amount=contract_overrides.get("penalty_amount"),
        trial_price=contract_overrides.get("trial_price"),
        trial_count=contract_overrides.get("trial_count"),
        contract_notes=contract_overrides.get("contract_notes"),
    )
    # Convert string status to enum for convenience.
    if isinstance(overrides.get("status"), str):
        overrides["status"] = MatchStatus(overrides["status"])
    defaults.update(overrides)
    return Match(contract=contract, **defaults)


# ━━━━━━━━━━ Create match ━━━━━━━━━━

class TestCreateMatch:
    ENDPOINT = "/api/matches"

    def test_create_success(self, client, parent_headers, mock_conn):
        """Parent creates a match invitation successfully."""
        with (
            patch(_MATCH_REPO_PATH) as MockMatchRepo,
            patch(_CATALOG_PATH) as MockCatalog,
        ):
            catalog = MockCatalog.return_value
            catalog.get_student_owner_for_update.return_value = 1  # parent
            catalog.lock_tutor_for_update.return_value = True
            catalog.tutor_teaches_subject.return_value = True
            catalog.get_active_student_count.return_value = 0
            catalog.get_max_students.return_value = 5

            match_repo = MockMatchRepo.return_value
            match_repo.check_duplicate_active.return_value = False
            match_repo.create.return_value = 100

            resp = client.post(self.ENDPOINT, json={
                "tutor_id": 1, "student_id": 1, "subject_id": 2,
                "hourly_rate": 600, "sessions_per_week": 2,
            }, headers=parent_headers)

        assert resp.status_code == 200
        assert resp.json()["data"]["match_id"] == 100

    def test_create_not_parent_role(self, client, tutor_headers):
        """Tutor role cannot create a match (403)."""
        resp = client.post(self.ENDPOINT, json={
            "tutor_id": 1, "student_id": 1, "subject_id": 2,
            "hourly_rate": 600, "sessions_per_week": 2,
        }, headers=tutor_headers)
        assert resp.status_code == 403

    def test_create_duplicate_active(self, client, parent_headers, mock_conn):
        """Duplicate match returns 409."""
        with (
            patch(_MATCH_REPO_PATH) as MockMatchRepo,
            patch(_CATALOG_PATH) as MockCatalog,
        ):
            catalog = MockCatalog.return_value
            catalog.get_student_owner_for_update.return_value = 1
            catalog.lock_tutor_for_update.return_value = True
            catalog.tutor_teaches_subject.return_value = True

            match_repo = MockMatchRepo.return_value
            match_repo.check_duplicate_active.return_value = True

            resp = client.post(self.ENDPOINT, json={
                "tutor_id": 1, "student_id": 1, "subject_id": 2,
                "hourly_rate": 600, "sessions_per_week": 2,
            }, headers=parent_headers)

        assert resp.status_code == 409


# ━━━━━━━━━━ State-machine transitions ━━━━━━━━━━

class TestMatchStatusTransitions:
    ENDPOINT = "/api/matches/{match_id}/status"

    def _patch_and_call(self, client, headers, match_id, match_entity, action, reason=None):
        """Helper: patch PostgresMatchRepository and send PATCH request."""
        with (
            patch(_MATCH_REPO_PATH) as MockRepo,
            patch(_CATALOG_PATH) as MockCatalog,
        ):
            repo = MockRepo.return_value
            repo.find_by_id.return_value = match_entity
            # B1: the paused→active resume path now re-checks capacity via
            # the catalog. Default the mock to "has capacity" so tests that
            # don't explicitly care about capacity keep passing.
            catalog = MockCatalog.return_value
            catalog.lock_tutor_for_update.return_value = True
            catalog.get_active_student_count.return_value = 0
            catalog.get_max_students.return_value = 5
            body = {"action": action}
            if reason:
                body["reason"] = reason
            return client.patch(
                self.ENDPOINT.format(match_id=match_id),
                json=body,
                headers=headers,
            )

    # ── Legal transitions ──

    def test_pending_cancel_by_parent(self, client, parent_headers):
        """pending → cancelled (parent)."""
        resp = self._patch_and_call(client, parent_headers, 1,
                                    _match_entity(status="pending"), "cancel")
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "cancelled"

    def test_pending_reject_by_tutor(self, client, tutor_headers):
        """pending → rejected (tutor)."""
        resp = self._patch_and_call(client, tutor_headers, 1,
                                    _match_entity(status="pending"), "reject")
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "rejected"

    def test_pending_accept_to_trial(self, client, tutor_headers):
        """pending → trial (tutor accepts, trial requested)."""
        resp = self._patch_and_call(client, tutor_headers, 1,
                                    _match_entity(status="pending", want_trial=True),
                                    "accept")
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "trial"

    def test_pending_accept_to_active(self, client, tutor_headers):
        """pending → active (tutor accepts, no trial)."""
        resp = self._patch_and_call(client, tutor_headers, 1,
                                    _match_entity(status="pending", want_trial=False),
                                    "accept")
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "active"

    def test_trial_confirm(self, client, tutor_headers):
        """trial → active."""
        resp = self._patch_and_call(client, tutor_headers, 1,
                                    _match_entity(status="trial"), "confirm_trial")
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "active"

    def test_trial_reject(self, client, parent_headers):
        """trial → rejected."""
        resp = self._patch_and_call(client, parent_headers, 1,
                                    _match_entity(status="trial"), "reject_trial")
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "rejected"

    def test_active_pause(self, client, tutor_headers):
        """active → paused."""
        resp = self._patch_and_call(client, tutor_headers, 1,
                                    _match_entity(status="active"), "pause")
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "paused"

    def test_paused_resume(self, client, parent_headers):
        """paused → active."""
        resp = self._patch_and_call(client, parent_headers, 1,
                                    _match_entity(status="paused"), "resume")
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "active"

    def test_active_terminate(self, client, tutor_headers):
        """active → terminating."""
        resp = self._patch_and_call(
            client, tutor_headers, 1, _match_entity(status="active"),
            "terminate", reason="搬家了",
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "terminating"

    def test_terminating_agree(self, client, parent_headers):
        """terminating → ended (the other party agrees)."""
        resp = self._patch_and_call(
            client, parent_headers, 1,
            _match_entity(status="terminating", terminated_by=2),
            "agree_terminate",
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "ended"

    def test_terminating_disagree(self, client, parent_headers):
        """terminating → previous status (the other party disagrees).

        The service re-reads the match inside a transaction; stub find_by_id
        to return a fresh TERMINATING entity on both calls.
        """
        entity = _match_entity(
            status="terminating",
            terminated_by=2,
            termination_reason="active|搬家了",
        )
        with (
            patch(_MATCH_REPO_PATH) as MockRepo,
            patch(_CATALOG_PATH),
        ):
            repo = MockRepo.return_value
            repo.find_by_id.return_value = entity
            resp = client.patch(
                self.ENDPOINT.format(match_id=1),
                json={"action": "disagree_terminate"},
                headers=parent_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "active"

    # ── Illegal transitions ──

    def test_illegal_transition_rejected(self, client, tutor_headers):
        """Cannot re-operate on a completed match."""
        resp = self._patch_and_call(client, tutor_headers, 1,
                                    _match_entity(status="ended"), "accept")
        assert resp.status_code == 400
        assert "無法" in resp.json()["message"]

    def test_pending_cannot_pause(self, client, tutor_headers):
        """pending cannot be paused."""
        resp = self._patch_and_call(client, tutor_headers, 1,
                                    _match_entity(status="pending"), "pause")
        assert resp.status_code == 400

    # ── Permission checks ──

    def test_parent_cannot_accept(self, client, parent_headers):
        """Parent cannot execute accept (tutor-only)."""
        resp = self._patch_and_call(client, parent_headers, 1,
                                    _match_entity(status="pending"), "accept")
        assert resp.status_code == 403

    def test_tutor_cannot_cancel(self, client, tutor_headers):
        """Tutor cannot cancel (parent-only)."""
        resp = self._patch_and_call(client, tutor_headers, 1,
                                    _match_entity(status="pending"), "cancel")
        assert resp.status_code == 403

    def test_terminate_requires_reason(self, client, tutor_headers):
        """Termination requires a reason."""
        resp = self._patch_and_call(client, tutor_headers, 1,
                                    _match_entity(status="active"), "terminate")
        assert resp.status_code == 400
        assert "原因" in resp.json()["message"]

    def test_terminator_cannot_agree_own(self, client, tutor_headers):
        """The party who initiated termination cannot also agree."""
        resp = self._patch_and_call(
            client, tutor_headers, 1,
            _match_entity(status="terminating", terminated_by=2),
            "agree_terminate",
        )
        assert resp.status_code == 403
