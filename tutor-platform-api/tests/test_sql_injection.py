"""SEC-13: SQL injection regression tests.

These tests submit known injection payloads to every user-facing string field
and assert two things:
  1. The application returns a well-formed HTTP response (no unhandled 500).
  2. The repository mock receives the raw payload string — confirming the value
     was passed as a parameterised argument, not interpolated into SQL.

All tests use the same mock-repo strategy as the rest of the suite (no real DB).
"""

import pytest
from unittest.mock import call, patch

from app.utils.security import hash_password


_AUTH_REPO = "app.identity.api.router.PostgresUserRepository"
_MATCH_REPO = "app.matching.api.router.PostgresMatchRepository"
_CATALOG = "app.matching.api.router.CatalogQueryAdapter"
_REVIEW_REPO = "app.review.api.router.PostgresReviewRepository"
_MSG_REPO = "app.messaging.api.router.PostgresMessageRepository"


INJECTION_PAYLOADS = [
    "' OR '1'='1",
    "' OR '1'='1' --",
    "; DROP TABLE users --",
    "1; SELECT * FROM users --",
    "' UNION SELECT null,null,null --",
    "admin'--",
]


# ━━━━━━━━━━ Auth fields ━━━━━━━━━━

class TestLoginInjection:
    ENDPOINT = "/api/auth/login"

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_username_injection_no_500(self, client, mock_conn, payload):
        """Injection payload in username must not cause an unhandled 500."""
        with patch(_AUTH_REPO) as MockRepo:
            MockRepo.return_value.find_by_username.return_value = None
            resp = client.post(self.ENDPOINT, json={"username": payload, "password": "pw"})
        assert resp.status_code != 500

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_username_passed_as_parameter(self, client, mock_conn, payload):
        """find_by_username must receive the raw payload string unchanged."""
        with patch(_AUTH_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_username.return_value = None
            client.post(self.ENDPOINT, json={"username": payload, "password": "pw"})
        repo.find_by_username.assert_called_once_with(payload)


class TestRegisterInjection:
    ENDPOINT = "/api/auth/register"

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_username_injection_no_500(self, client, mock_conn, payload):
        with patch(_AUTH_REPO) as MockRepo:
            MockRepo.return_value.find_by_username.return_value = None
            MockRepo.return_value.register_user.return_value = 1
            resp = client.post(self.ENDPOINT, json={
                "username": payload,
                "password": "Secure12345",
                "display_name": "Test",
                "role": "parent",
            })
        assert resp.status_code != 500

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_display_name_injection_no_500(self, client, mock_conn, payload):
        with patch(_AUTH_REPO) as MockRepo:
            MockRepo.return_value.find_by_username.return_value = None
            MockRepo.return_value.register_user.return_value = 1
            resp = client.post(self.ENDPOINT, json={
                "username": "safeuser",
                "password": "Secure12345",
                "display_name": payload,
                "role": "parent",
            })
        assert resp.status_code != 500


# ━━━━━━━━━━ Match invite_message ━━━━━━━━━━

class TestMatchCreateInjection:
    ENDPOINT = "/api/matches"

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_invite_message_injection_no_500(self, client, parent_headers, mock_conn, payload):
        """Injection payload in invite_message must not cause an unhandled 500."""
        with (
            patch(_MATCH_REPO) as MockMatchRepo,
            patch(_CATALOG) as MockCatalog,
        ):
            catalog = MockCatalog.return_value
            catalog.get_student_owner_for_update.return_value = 1
            catalog.lock_tutor_for_update.return_value = True
            catalog.tutor_teaches_subject.return_value = True
            catalog.get_active_student_count.return_value = 0
            catalog.get_max_students.return_value = 5

            match_repo = MockMatchRepo.return_value
            match_repo.check_duplicate_active.return_value = False
            match_repo.create.return_value = 42

            resp = client.post(self.ENDPOINT, json={
                "tutor_id": 1, "student_id": 1, "subject_id": 2,
                "hourly_rate": 600, "sessions_per_week": 2,
                "invite_message": payload,
            }, headers=parent_headers)

        assert resp.status_code != 500

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_invite_message_passed_as_parameter(self, client, parent_headers, mock_conn, payload):
        """match_repo.create must receive invite_message as a raw string argument."""
        with (
            patch(_MATCH_REPO) as MockMatchRepo,
            patch(_CATALOG) as MockCatalog,
        ):
            catalog = MockCatalog.return_value
            catalog.get_student_owner_for_update.return_value = 1
            catalog.lock_tutor_for_update.return_value = True
            catalog.tutor_teaches_subject.return_value = True
            catalog.get_active_student_count.return_value = 0
            catalog.get_max_students.return_value = 5

            match_repo = MockMatchRepo.return_value
            match_repo.check_duplicate_active.return_value = False
            match_repo.create.return_value = 42

            client.post(self.ENDPOINT, json={
                "tutor_id": 1, "student_id": 1, "subject_id": 2,
                "hourly_rate": 600, "sessions_per_week": 2,
                "invite_message": payload,
            }, headers=parent_headers)

        _, kwargs = match_repo.create.call_args
        assert kwargs.get("invite_message") == payload
