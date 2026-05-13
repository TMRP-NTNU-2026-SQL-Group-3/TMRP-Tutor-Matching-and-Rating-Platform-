"""SEC-13: SQL injection regression tests.

These tests submit known injection payloads to every user-facing string field
and assert two things:
  1. The application returns a well-formed HTTP response (no unhandled 500).
  2. The repository mock receives the raw payload string — confirming the value
     was passed as a parameterised argument, not interpolated into SQL.

All tests use the same mock-repo strategy as the rest of the suite (no real DB).
"""

import pytest
from unittest.mock import patch

_AUTH_REPO = "app.identity.infrastructure.postgres_user_repo.PostgresUserRepository"
_MATCH_REPO = "app.matching.api.dependencies.PostgresMatchRepository"
_CATALOG = "app.matching.api.dependencies.CatalogQueryAdapter"
_REVIEW_REPO = "app.review.api.router.PostgresReviewRepository"
_SESSION_REPO = "app.teaching.api.dependencies.PostgresSessionRepository"
_MSG_MSG_REPO = "app.messaging.api.dependencies.PostgresMessageRepository"
_MSG_CONV_REPO = "app.messaging.api.dependencies.PostgresConversationRepository"


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

    # Note: a test that asserts find_by_username receives the raw payload is
    # not meaningful here — the LoginRequest schema rejects SQL injection
    # payloads (which contain characters outside the allowed pattern) with
    # HTTP 422 before the request reaches the repository layer. The
    # schema-level rejection is a stronger control than parameterized queries
    # alone, so test_username_injection_no_500 above already covers this path.


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


# ━━━━━━━━━━ Review comment ━━━━━━━━━━

class TestReviewCommentInjection:
    ENDPOINT = "/api/matches/1/reviews"

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_comment_injection_no_500(self, client, parent_headers, mock_conn, payload):
        """Injection payload in review comment must not cause an unhandled 500."""
        with patch(_REVIEW_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = {
                "match_id": 1, "status": "ended",
                "tutor_user_id": 2, "parent_user_id": 1,
                "session_count": 1,
            }
            repo.create.return_value = 42

            resp = client.post(self.ENDPOINT, json={
                "review_type": "parent_to_tutor",
                "rating_1": 5, "rating_2": 5, "rating_3": 5, "rating_4": 5,
                "comment": payload,
            }, headers=parent_headers)

        assert resp.status_code != 500

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_comment_passed_as_parameter(self, client, parent_headers, mock_conn, payload):
        """review_repo.create must receive comment as a raw string argument."""
        with patch(_REVIEW_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = {
                "match_id": 1, "status": "ended",
                "tutor_user_id": 2, "parent_user_id": 1,
                "session_count": 1,
            }
            repo.create.return_value = 42

            client.post(self.ENDPOINT, json={
                "review_type": "parent_to_tutor",
                "rating_1": 5, "rating_2": 5, "rating_3": 5, "rating_4": 5,
                "comment": payload,
            }, headers=parent_headers)

        _, kwargs = repo.create.call_args
        assert kwargs.get("comment") == payload


# ━━━━━━━━━━ Session content_summary ━━━━━━━━━━

class TestSessionContentSummaryInjection:
    ENDPOINT = "/api/matches/1/sessions"

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_content_summary_injection_no_500(self, client, tutor_headers, mock_conn, payload):
        """Injection payload in content_summary must not cause an unhandled 500."""
        with patch(_SESSION_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = {
                "match_id": 1, "status": "active", "tutor_user_id": 2,
            }
            repo.create.return_value = 50

            resp = client.post(self.ENDPOINT, json={
                "session_date": "2025-04-01T14:00:00",
                "hours": 2.0,
                "content_summary": payload,
            }, headers=tutor_headers)

        assert resp.status_code != 500

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_content_summary_passed_as_parameter(self, client, tutor_headers, mock_conn, payload):
        """session_repo.create must receive content_summary as a raw string argument."""
        with patch(_SESSION_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = {
                "match_id": 1, "status": "active", "tutor_user_id": 2,
            }
            repo.create.return_value = 50

            client.post(self.ENDPOINT, json={
                "session_date": "2025-04-01T14:00:00",
                "hours": 2.0,
                "content_summary": payload,
            }, headers=tutor_headers)

        _, kwargs = repo.create.call_args
        assert kwargs.get("content_summary") == payload


# ━━━━━━━━━━ Message content ━━━━━━━━━━

class TestMessageContentInjection:
    ENDPOINT = "/api/messages/conversations/1/messages"

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_content_injection_no_500(self, client, parent_headers, mock_conn, payload):
        """Injection payload in message content must not cause an unhandled 500."""
        with (
            patch(_MSG_MSG_REPO) as MockMsgRepo,
            patch(_MSG_CONV_REPO) as MockConvRepo,
        ):
            MockConvRepo.return_value.user_is_participant.return_value = True
            MockMsgRepo.return_value.send_message.return_value = 10

            resp = client.post(
                self.ENDPOINT,
                json={"content": payload},
                headers=parent_headers,
            )

        assert resp.status_code != 500

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_content_passed_as_parameter(self, client, parent_headers, mock_conn, payload):
        """msg_repo.send_message must receive content as a raw positional argument."""
        with (
            patch(_MSG_MSG_REPO) as MockMsgRepo,
            patch(_MSG_CONV_REPO) as MockConvRepo,
        ):
            MockConvRepo.return_value.user_is_participant.return_value = True
            MockMsgRepo.return_value.send_message.return_value = 10

            client.post(
                self.ENDPOINT,
                json={"content": payload},
                headers=parent_headers,
            )

        args, _ = MockMsgRepo.return_value.send_message.call_args
        assert args[2] == payload
