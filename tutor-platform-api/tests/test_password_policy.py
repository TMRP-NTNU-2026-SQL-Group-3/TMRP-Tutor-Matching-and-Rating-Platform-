"""Password security policy: PUT /api/auth/password and login lockout.

Tests:
- Correct-password change succeeds.
- Wrong current password is rejected (400).
- Reuse of the current password is rejected (422).
- Reuse of a password from history is rejected (422).
- Login is rate-limited after the per-username bucket is exhausted (429).
"""

from unittest.mock import patch

from app.shared.infrastructure.security import hash_password


_USER_REPO = "app.identity.infrastructure.postgres_user_repo.PostgresUserRepository"
_CSRF = "test-csrf-token"


class TestChangePassword:
    ENDPOINT = "/api/auth/password"

    def test_change_password_success(self, client, parent_headers):
        """Providing the correct current password and a different new password succeeds."""
        hashed = hash_password("OldPassword1")
        with patch(_USER_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_id.return_value = {
                "user_id": 1, "password_hash": hashed,
                "username": "parent01", "role": "parent",
            }
            repo.get_recent_password_hashes.return_value = []
            repo.save_password_history.return_value = None
            repo.update_password.return_value = None

            resp = client.put(
                self.ENDPOINT,
                json={"current_password": "OldPassword1", "new_password": "NewPassword2"},
                headers={**parent_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_change_password_wrong_current_returns_400(self, client, parent_headers):
        """Supplying the wrong current password is rejected before any write occurs."""
        hashed = hash_password("CorrectPassword1")
        with patch(_USER_REPO) as MockRepo:
            MockRepo.return_value.find_by_id.return_value = {
                "user_id": 1, "password_hash": hashed,
            }
            resp = client.put(
                self.ENDPOINT,
                json={"current_password": "WrongPassword2", "new_password": "AnotherPass3"},
                headers={**parent_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 400

    def test_change_password_reuse_current_returns_422(self, client, parent_headers):
        """Attempting to change to the same password already in use is rejected (SEC-06)."""
        hashed = hash_password("SamePassword1")
        with patch(_USER_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_id.return_value = {
                "user_id": 1, "password_hash": hashed,
            }
            repo.get_recent_password_hashes.return_value = []

            resp = client.put(
                self.ENDPOINT,
                json={"current_password": "SamePassword1", "new_password": "SamePassword1"},
                headers={**parent_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 422

    def test_change_password_reuse_from_history_returns_422(self, client, parent_headers):
        """A password matching one of the last 5 stored hashes is rejected (SEC-06)."""
        hashed_current = hash_password("CurrentPass1")
        hashed_history = hash_password("HistoryPass2")
        with patch(_USER_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_id.return_value = {
                "user_id": 1, "password_hash": hashed_current,
            }
            repo.get_recent_password_hashes.return_value = [hashed_history]

            resp = client.put(
                self.ENDPOINT,
                json={"current_password": "CurrentPass1", "new_password": "HistoryPass2"},
                headers={**parent_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 422

    def test_change_password_saves_history_on_success(self, client, parent_headers):
        """save_password_history is called with the old hash before updating (SEC-06)."""
        hashed = hash_password("OldPw12345")
        with patch(_USER_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_id.return_value = {
                "user_id": 1, "password_hash": hashed,
            }
            repo.get_recent_password_hashes.return_value = []
            repo.save_password_history.return_value = None
            repo.update_password.return_value = None

            client.put(
                self.ENDPOINT,
                json={"current_password": "OldPw12345", "new_password": "NewPw67890"},
                headers={**parent_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        repo.save_password_history.assert_called_once_with(1, hashed)


class TestLoginLockout:
    """Per-username rate limit on POST /api/auth/login (H-03)."""

    ENDPOINT = "/api/auth/login"

    def test_lockout_returns_429_when_bucket_exhausted(self, client):
        """When the per-username bucket is full the login endpoint returns 429.

        Overrides the global True-returning mock with a False-returning one so
        the in-router check_and_record_bucket call sees the exhausted state.
        """
        with patch("app.identity.api.router.check_and_record_bucket", return_value=False):
            resp = client.post(
                self.ENDPOINT,
                json={"username": "targeted_user", "password": "anypassword"},
            )

        assert resp.status_code == 429
        assert "嘗試次數過多" in resp.json()["message"]
