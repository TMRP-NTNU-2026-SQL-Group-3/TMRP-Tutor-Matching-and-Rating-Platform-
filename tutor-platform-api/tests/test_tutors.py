"""Tutor catalog router tests.

Key coverage:
  - F-09: tutors are forbidden from searching the tutor catalog (spec §4.2).
  - Access-control matrix for /me, /{id}, and profile-mutation endpoints.

PostgresTutorRepository and TutorService are patched at their construction
sites inside app.catalog.api.dependencies so the DI chain returns controlled
mocks without touching any real infrastructure.
"""

from unittest.mock import patch

_TUTOR_REPO = "app.catalog.api.dependencies.PostgresTutorRepository"
_TUTOR_SERVICE = "app.catalog.api.dependencies.TutorService"
_CSRF = "test-csrf-token"


class TestSearchTutors:
    ENDPOINT = "/api/tutors"

    def test_parent_can_search_tutors(self, client, parent_headers, mock_conn):
        """Parents are permitted to browse the tutor catalog."""
        with patch(_TUTOR_REPO) as MockRepo, patch(_TUTOR_SERVICE) as MockService:
            MockRepo.return_value.search_with_stats.return_value = (
                [{"tutor_id": 1, "display_name": "陳老師"}], 1,
            )
            svc = MockService.return_value
            svc.normalize_search_row.side_effect = lambda t: t
            svc.apply_visibility.side_effect = lambda t: t

            resp = client.get(self.ENDPOINT, headers=parent_headers)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["tutor_id"] == 1

    def test_admin_can_search_tutors(self, client, admin_headers, mock_conn):
        """Admins may also access the tutor search endpoint."""
        with patch(_TUTOR_REPO) as MockRepo, patch(_TUTOR_SERVICE) as MockService:
            MockRepo.return_value.search_with_stats.return_value = ([], 0)
            MockService.return_value.normalize_search_row.side_effect = lambda t: t
            MockService.return_value.apply_visibility.side_effect = lambda t: t

            resp = client.get(self.ENDPOINT, headers=admin_headers)

        assert resp.status_code == 200

    def test_tutor_cannot_search_tutors(self, client, tutor_headers, mock_conn):
        """Spec §4.2: tutors are prohibited from searching the tutor catalog."""
        resp = client.get(self.ENDPOINT, headers=tutor_headers)
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, client):
        """Anonymous browse of the tutor catalog returns 401 — intentional security invariant.

        SEC-15: GET /api/tutors requires authentication. Unlike GET /api/subjects
        (public catalog), tutor search exposes PII (display names, school
        affiliations, hourly rates) that the platform restricts to verified
        account holders. Removing get_current_user from the Depends() chain
        must cause this test to fail.
        """
        resp = client.get(self.ENDPOINT)
        assert resp.status_code == 401


class TestGetMyTutorProfile:
    ENDPOINT = "/api/tutors/me"

    def test_tutor_gets_own_profile(self, client, tutor_headers, mock_conn):
        """Authenticated tutor retrieves their full profile including subjects and availability."""
        with patch(_TUTOR_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_user_id.return_value = {"tutor_id": 1, "user_id": 2, "bio": "experienced"}
            repo.get_subjects.return_value = [{"subject_id": 1}]
            repo.get_availability.return_value = []

            resp = client.get(self.ENDPOINT, headers=tutor_headers)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["tutor_id"] == 1
        assert data["subjects"] == [{"subject_id": 1}]

    def test_parent_cannot_access_me_endpoint(self, client, parent_headers, mock_conn):
        """Parent role is forbidden on /tutors/me."""
        resp = client.get(self.ENDPOINT, headers=parent_headers)
        assert resp.status_code == 403

    def test_tutor_not_in_db_returns_404(self, client, tutor_headers, mock_conn):
        """A valid tutor JWT whose profile row is missing returns 404."""
        with patch(_TUTOR_REPO) as MockRepo:
            MockRepo.return_value.find_by_user_id.return_value = None

            resp = client.get(self.ENDPOINT, headers=tutor_headers)

        assert resp.status_code == 404


class TestGetTutorDetail:
    def test_parent_can_view_tutor_detail(self, client, parent_headers, mock_conn):
        """Any authenticated user can view a tutor's public detail page."""
        with patch(_TUTOR_REPO) as MockRepo, patch(_TUTOR_SERVICE) as MockService:
            MockRepo.return_value.find_detail.return_value = {
                "tutor_id": 1, "user_id": 10,
                "avg_r1": 4.5, "avg_r2": 4.0, "avg_r3": 4.2, "avg_r4": 4.8,
                "review_count": 3,
            }
            MockService.return_value.apply_visibility.side_effect = lambda t: t

            resp = client.get("/api/tutors/1", headers=parent_headers)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["tutor_id"] == 1
        assert "rating" in data

    def test_tutor_not_found_returns_404(self, client, parent_headers, mock_conn):
        """Non-existent tutor_id returns 404."""
        with patch(_TUTOR_REPO) as MockRepo, patch(_TUTOR_SERVICE) as MockService:  # noqa: F841
            MockRepo.return_value.find_detail.return_value = None

            resp = client.get("/api/tutors/999", headers=parent_headers)

        assert resp.status_code == 404

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/api/tutors/1")
        assert resp.status_code == 401


class TestUpdateTutorProfile:
    ENDPOINT = "/api/tutors/profile"

    def test_tutor_can_update_own_profile(self, client, tutor_headers, mock_conn):
        """Tutor can update their own bio."""
        with patch(_TUTOR_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_user_id.return_value = {"tutor_id": 1}
            repo.update_profile.return_value = None

            resp = client.put(
                self.ENDPOINT,
                json={"self_intro": "5 years experience"},
                headers={**tutor_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 200

    def test_parent_cannot_update_tutor_profile(self, client, parent_headers, mock_conn):
        """Profile mutation endpoints require tutor role."""
        resp = client.put(
            self.ENDPOINT,
            json={"bio": "fake"},
            headers={**parent_headers, "X-CSRF-Token": _CSRF},
            cookies={"csrf_token": _CSRF},
        )
        assert resp.status_code == 403
