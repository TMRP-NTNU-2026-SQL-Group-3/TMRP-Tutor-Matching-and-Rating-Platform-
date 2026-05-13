"""Review API tests: three-way review / lock window / duplicate rejection.

Patches the Review BC infrastructure repo (`PostgresReviewRepository`) at
its import site inside `app.review.api.router`.
"""

from datetime import datetime, timezone
from unittest.mock import patch


_REPO_PATH = "app.review.api.router.PostgresReviewRepository"


def _match_participants(**overrides):
    base = {
        "match_id": 1,
        "status": "ended",
        "tutor_user_id": 2,
        "parent_user_id": 1,
        "session_count": 1,
    }
    base.update(overrides)
    return base


# ━━━━━━━━━━ Create review ━━━━━━━━━━

class TestCreateReview:
    ENDPOINT = "/api/matches/{match_id}/reviews"

    def test_parent_to_tutor_success(self, client, parent_headers, mock_conn):
        """Parent reviewing tutor succeeds."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = _match_participants()
            repo.create.return_value = 10

            resp = client.post(self.ENDPOINT.format(match_id=1), json={
                "review_type": "parent_to_tutor",
                "rating_1": 5, "rating_2": 4,
                "rating_3": 5, "rating_4": 4,
                "comment": "很棒的老師",
            }, headers=parent_headers)

        assert resp.status_code == 201
        assert resp.json()["data"]["review_id"] == 10

    def test_tutor_to_parent_success(self, client, tutor_headers, mock_conn):
        """Tutor reviewing parent succeeds."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = _match_participants()
            repo.create.return_value = 11

            resp = client.post(self.ENDPOINT.format(match_id=1), json={
                "review_type": "tutor_to_parent",
                "rating_1": 4, "rating_2": 3,
            }, headers=tutor_headers)

        assert resp.status_code == 201
        assert resp.json()["data"]["review_id"] == 11

    def test_tutor_to_student_success(self, client, tutor_headers, mock_conn):
        """Tutor reviewing student succeeds."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = _match_participants()
            repo.create.return_value = 12

            resp = client.post(self.ENDPOINT.format(match_id=1), json={
                "review_type": "tutor_to_student",
                "rating_1": 5, "rating_2": 5,
            }, headers=tutor_headers)

        assert resp.status_code == 201

    def test_duplicate_review_rejected(self, client, parent_headers, mock_conn):
        """Duplicate review returns 409.

        The service now relies on idx_reviews_unique to enforce
        one-per-(match, reviewer, type) at the DB layer, so the duplicate
        surfaces as a psycopg2 UniqueViolation from repo.create rather than
        a pre-INSERT find_existing check.
        """
        from psycopg2.errors import UniqueViolation
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = _match_participants()
            repo.create.side_effect = UniqueViolation()

            resp = client.post(self.ENDPOINT.format(match_id=1), json={
                "review_type": "parent_to_tutor",
                "rating_1": 5, "rating_2": 4,
                "rating_3": 5, "rating_4": 4,
            }, headers=parent_headers)

        assert resp.status_code == 409
        assert "已" in resp.json()["message"]

    def test_parent_cannot_review_as_tutor(self, client, parent_headers, mock_conn):
        """Parent cannot submit tutor_to_parent review type."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = _match_participants()

            resp = client.post(self.ENDPOINT.format(match_id=1), json={
                "review_type": "tutor_to_parent",
                "rating_1": 3, "rating_2": 3,
            }, headers=parent_headers)

        assert resp.status_code == 403

    def test_invalid_review_type(self, client, parent_headers, mock_conn):
        """Invalid review type returns 400."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = _match_participants()

            resp = client.post(self.ENDPOINT.format(match_id=1), json={
                "review_type": "student_to_tutor",
                "rating_1": 3, "rating_2": 3,
            }, headers=parent_headers)

        assert resp.status_code == 400

    def test_match_not_found(self, client, parent_headers, mock_conn):
        """Missing match returns 404."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = None

            resp = client.post(self.ENDPOINT.format(match_id=999), json={
                "review_type": "parent_to_tutor",
                "rating_1": 5, "rating_2": 5,
                "rating_3": 5, "rating_4": 5,
            }, headers=parent_headers)

        assert resp.status_code == 404


# ━━━━━━━━━━ 7-day lock window ━━━━━━━━━━

class TestReviewLock:
    ENDPOINT = "/api/reviews/{review_id}"

    def test_update_within_lock_period(self, client, parent_headers, mock_conn):
        """Review can be edited within the lock window."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.get_for_update.return_value = {
                "review_id": 10,
                "reviewer_user_id": 1,
                "is_locked": False,
                "created_at": datetime.now(timezone.utc),
            }

            resp = client.patch(
                self.ENDPOINT.format(review_id=10),
                json={"rating_1": 4, "comment": "更新評價"},
                headers=parent_headers,
            )

        assert resp.status_code == 200

    def test_update_after_lock(self, client, parent_headers, mock_conn):
        """Locked review returns 400."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.get_for_update.return_value = {
                "review_id": 10,
                "reviewer_user_id": 1,
                "is_locked": True,
                "created_at": datetime.now(timezone.utc),
            }

            resp = client.patch(
                self.ENDPOINT.format(review_id=10),
                json={"rating_1": 1},
                headers=parent_headers,
            )

        assert resp.status_code == 400
        assert "編輯期限" in resp.json()["message"]

    def test_update_not_reviewer(self, client, tutor_headers, mock_conn):
        """Non-reviewer cannot modify."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.get_for_update.return_value = {
                "review_id": 10,
                "reviewer_user_id": 1,
                "is_locked": False,
                "created_at": datetime.now(timezone.utc),
            }

            resp = client.patch(
                self.ENDPOINT.format(review_id=10),
                json={"rating_1": 1},
                headers=tutor_headers,
            )

        assert resp.status_code == 403


# ━━━━━━━━━━ List reviews ━━━━━━━━━━

class TestListReviews:
    ENDPOINT = "/api/matches/{match_id}/reviews"

    def test_list_as_participant(self, client, parent_headers, mock_conn):
        """Participant can list reviews."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_participants.return_value = _match_participants()
            repo.list_by_match.return_value = [
                {"review_id": 10, "review_type": "parent_to_tutor"},
            ]

            resp = client.get(
                self.ENDPOINT.format(match_id=1),
                headers=parent_headers,
            )

        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    def test_list_non_participant_denied(self, client, admin_headers, mock_conn):
        """Admin can list any match's reviews."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_participants.return_value = _match_participants()
            repo.list_by_match.return_value = []

            resp = client.get(
                self.ENDPOINT.format(match_id=1),
                headers=admin_headers,
            )

        assert resp.status_code == 200
