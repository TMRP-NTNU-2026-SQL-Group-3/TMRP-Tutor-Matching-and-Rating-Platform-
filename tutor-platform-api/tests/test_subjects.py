"""Subject catalog router tests.

The subjects endpoint is public — no authentication is required.
BaseRepository is patched at its import site in subject_router so the
mock_conn does not need to expose real cursor iteration.
"""

from unittest.mock import patch

_BASE_REPO = "app.catalog.api.subject_router.BaseRepository"


class TestListSubjects:
    ENDPOINT = "/api/subjects"

    def test_public_no_auth_required(self, client, mock_conn):
        """Subjects list is accessible without any authentication token."""
        with patch(_BASE_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.fetch_all.return_value = [
                {"subject_id": 1, "subject_name": "數學", "category": "理科"},
                {"subject_id": 2, "subject_name": "英文", "category": "語文"},
            ]
            repo.fetch_one.return_value = {"cnt": 2}

            resp = client.get(self.ENDPOINT)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["subject_id"] == 1

    def test_empty_table_returns_valid_envelope(self, client, mock_conn):
        """An empty subjects table still returns a well-formed pagination envelope."""
        with patch(_BASE_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.fetch_all.return_value = []
            repo.fetch_one.return_value = {"cnt": 0}

            resp = client.get(self.ENDPOINT)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 0
        assert data["items"] == []
        assert data["total_pages"] == 1
        assert data["has_next"] is False
        assert data["has_prev"] is False

    def test_total_pages_calculated_correctly(self, client, mock_conn):
        """total_pages = ceil(total / page_size); has_next flags the next page."""
        with patch(_BASE_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.fetch_all.return_value = [
                {"subject_id": i, "subject_name": f"科目{i}", "category": "測試"}
                for i in range(1, 4)
            ]
            repo.fetch_one.return_value = {"cnt": 7}

            resp = client.get(f"{self.ENDPOINT}?page=1&page_size=3")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_pages"] == 3
        assert data["has_next"] is True
        assert data["has_prev"] is False

    def test_authenticated_user_also_succeeds(self, client, parent_headers, mock_conn):
        """Authenticated users can also call the public subjects endpoint."""
        with patch(_BASE_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.fetch_all.return_value = [{"subject_id": 1, "subject_name": "物理", "category": "理科"}]
            repo.fetch_one.return_value = {"cnt": 1}

            resp = client.get(self.ENDPOINT, headers=parent_headers)

        assert resp.status_code == 200
