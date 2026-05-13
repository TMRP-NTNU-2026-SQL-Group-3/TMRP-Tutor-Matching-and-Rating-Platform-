"""Student router tests: list, add, update, delete.

After F-08, GET /api/students accepts both parent and tutor roles with
different query paths. All other mutating endpoints remain parent-only.
PostgresStudentRepository is patched at its import site in student_router.
"""

from unittest.mock import patch

_STUDENT_REPO = "app.catalog.api.student_router.PostgresStudentRepository"
_CSRF = "test-csrf-token"


class TestListStudents:
    ENDPOINT = "/api/students"

    def test_parent_sees_own_children(self, client, parent_headers, mock_conn):
        """Parent receives the students registered under their account."""
        with patch(_STUDENT_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_parent.return_value = [{"student_id": 1, "name": "小明"}]
            repo.count_by_parent.return_value = 1

            resp = client.get(self.ENDPOINT, headers=parent_headers)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["student_id"] == 1

    def test_tutor_sees_matched_students(self, client, tutor_headers, mock_conn):
        """Tutor receives students with active matches to them (spec §7.3)."""
        with patch(_STUDENT_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_tutor_user_id.return_value = [{"student_id": 3, "name": "小華"}]
            repo.count_by_tutor_user_id.return_value = 1

            resp = client.get(self.ENDPOINT, headers=tutor_headers)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["student_id"] == 3

    def test_unauthenticated_returns_401(self, client):
        """Missing token is rejected before any business logic runs."""
        resp = client.get(self.ENDPOINT)
        assert resp.status_code == 401

    def test_admin_cannot_list_students(self, client, admin_headers, mock_conn):
        """Admin role is not permitted on this endpoint."""
        resp = client.get(self.ENDPOINT, headers=admin_headers)
        assert resp.status_code == 403

    def test_parent_empty_list(self, client, parent_headers, mock_conn):
        """Parent with no children gets a valid empty-page envelope."""
        with patch(_STUDENT_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_parent.return_value = []
            repo.count_by_parent.return_value = 0

            resp = client.get(self.ENDPOINT, headers=parent_headers)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 0
        assert data["items"] == []
        assert data["total_pages"] == 1


class TestAddStudent:
    ENDPOINT = "/api/students"

    def test_parent_can_add_student(self, client, parent_headers, mock_conn):
        """Parent can register a new child."""
        with patch(_STUDENT_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.count_by_parent.return_value = 0
            repo.create.return_value = 5

            resp = client.post(
                self.ENDPOINT,
                json={"name": "小明", "school": "台北小學", "grade": "三年級"},
                headers={**parent_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 200
        assert resp.json()["data"]["student_id"] == 5

    def test_tutor_cannot_add_student(self, client, tutor_headers, mock_conn):
        """POST requires parent role; tutor role is forbidden."""
        resp = client.post(
            self.ENDPOINT,
            json={"name": "小明"},
            headers={**tutor_headers, "X-CSRF-Token": _CSRF},
            cookies={"csrf_token": _CSRF},
        )
        assert resp.status_code == 403

    def test_parent_at_cap_is_rejected(self, client, parent_headers, mock_conn):
        """Parent who has reached the per-account ceiling cannot add more."""
        with patch(_STUDENT_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.count_by_parent.return_value = 20

            resp = client.post(
                self.ENDPOINT,
                json={"name": "第二十一名"},
                headers={**parent_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 400


class TestUpdateStudent:
    def test_parent_can_update_own_student(self, client, parent_headers, mock_conn):
        """Parent can update a student they own."""
        with patch(_STUDENT_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_id_for_parent.return_value = {"student_id": 1, "name": "小明"}
            repo.update.return_value = None

            resp = client.put(
                "/api/students/1",
                json={"name": "小華"},
                headers={**parent_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 200
        assert resp.json()["data"]["student_id"] == 1

    def test_student_not_owned_returns_404(self, client, parent_headers, mock_conn):
        """Ownership predicate returning None maps to 404 (no ID enumeration)."""
        with patch(_STUDENT_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_id_for_parent.return_value = None

            resp = client.put(
                "/api/students/99",
                json={"name": "小華"},
                headers={**parent_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 404

    def test_empty_body_returns_400(self, client, parent_headers, mock_conn):
        """Sending no updatable fields is rejected before any DB write."""
        with patch(_STUDENT_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_id_for_parent.return_value = {"student_id": 1}

            resp = client.put(
                "/api/students/1",
                json={},
                headers={**parent_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 400


class TestDeleteStudent:
    def test_parent_can_delete_own_student(self, client, parent_headers, mock_conn):
        """Parent can delete a student they own."""
        with patch(_STUDENT_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_id_for_parent.return_value = {"student_id": 2}
            repo.delete.return_value = True

            resp = client.delete(
                "/api/students/2",
                headers={**parent_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 200
        assert resp.json()["data"]["student_id"] == 2

    def test_delete_not_owned_returns_404(self, client, parent_headers, mock_conn):
        """Attempting to delete a student not owned by the caller returns 404."""
        with patch(_STUDENT_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_id_for_parent.return_value = None

            resp = client.delete(
                "/api/students/99",
                headers={**parent_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 404
