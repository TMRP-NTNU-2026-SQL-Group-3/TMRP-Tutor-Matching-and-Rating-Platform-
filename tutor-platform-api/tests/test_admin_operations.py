"""Admin operation tests: anonymization, user password reset, and seed trigger.

All endpoints require admin role and CSRF double-submit.
TableAdminRepository is patched at its import site in
app.admin.api.dependencies so the mocked class is returned by get_admin_repo.
"""

import json
import sys
from unittest.mock import MagicMock, patch

# seed module lives inside the API container; install a lightweight stub so
# tests that hit POST /api/admin/seed do not fail on import.
if "seed" not in sys.modules:
    _seed_stub = MagicMock()
    sys.modules["seed"] = MagicMock()
    sys.modules["seed.generator"] = _seed_stub

_ADMIN_REPO = "app.admin.api.dependencies.TableAdminRepository"
_CSRF = "test-csrf-token"


class TestAdminAnonymize:
    def test_anonymize_parent_success(self, client, admin_headers):
        """Admin can anonymize a parent account that has no active matches."""
        with patch(_ADMIN_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.conn = MagicMock()
            repo.get_user_role.return_value = "parent"
            repo.count_admins.return_value = 2
            repo.anonymize_user.return_value = True
            repo.record_admin_action.return_value = None

            resp = client.post(
                "/api/admin/users/5/anonymize",
                headers={**admin_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 200
        assert resp.json()["data"]["user_id"] == 5

    def test_anonymize_self_is_blocked(self, client, admin_headers):
        """Admin cannot anonymize their own account (admin token sub = 99)."""
        resp = client.post(
            "/api/admin/users/99/anonymize",
            headers={**admin_headers, "X-CSRF-Token": _CSRF},
            cookies={"csrf_token": _CSRF},
        )
        assert resp.status_code == 400

    def test_anonymize_nonexistent_user_returns_404(self, client, admin_headers):
        """Attempting to anonymize a user_id not present in the DB returns 404."""
        with patch(_ADMIN_REPO) as MockRepo:
            MockRepo.return_value.get_user_role.return_value = None

            resp = client.post(
                "/api/admin/users/999/anonymize",
                headers={**admin_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 404

    def test_anonymize_last_admin_is_blocked(self, client, admin_headers):
        """Anonymizing the sole remaining admin is refused to preserve break-glass access."""
        with patch(_ADMIN_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.get_user_role.return_value = "admin"
            repo.count_admins.return_value = 1

            resp = client.post(
                "/api/admin/users/10/anonymize",
                headers={**admin_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 400

    def test_anonymize_requires_admin_role(self, client, parent_headers):
        """Non-admin callers receive 403 before any repository is consulted."""
        resp = client.post(
            "/api/admin/users/5/anonymize",
            headers={**parent_headers, "X-CSRF-Token": _CSRF},
            cookies={"csrf_token": _CSRF},
        )
        assert resp.status_code == 403


class TestAdminResetUserPassword:
    def test_reset_password_success(self, client, admin_headers):
        """Admin can reset any user's password when the account exists."""
        with patch(_ADMIN_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.conn = MagicMock()
            repo.reset_user_password.return_value = True
            repo.record_admin_action.return_value = None

            resp = client.post(
                "/api/admin/users/5/reset-password",
                json={"new_password": "SecurePass123"},
                headers={**admin_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 200
        assert resp.json()["data"]["user_id"] == 5

    def test_reset_password_user_not_found_returns_404(self, client, admin_headers):
        """Resetting the password for an unknown user_id returns 404."""
        with patch(_ADMIN_REPO) as MockRepo:
            repo = MockRepo.return_value
            repo.conn = MagicMock()
            repo.reset_user_password.return_value = False

            resp = client.post(
                "/api/admin/users/999/reset-password",
                json={"new_password": "SecurePass123"},
                headers={**admin_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 404

    def test_reset_password_weak_password_returns_422(self, client, admin_headers):
        """A new password that fails the strength validator is rejected by schema (422)."""
        resp = client.post(
            "/api/admin/users/5/reset-password",
            json={"new_password": "weak"},
            headers={**admin_headers, "X-CSRF-Token": _CSRF},
            cookies={"csrf_token": _CSRF},
        )
        assert resp.status_code == 422

    def test_reset_password_requires_admin_role(self, client, parent_headers):
        """Non-admin callers are rejected before the repository is consulted."""
        resp = client.post(
            "/api/admin/users/5/reset-password",
            json={"new_password": "SecurePass123"},
            headers={**parent_headers, "X-CSRF-Token": _CSRF},
            cookies={"csrf_token": _CSRF},
        )
        assert resp.status_code == 403


class TestAdminSeed:
    ENDPOINT = "/api/admin/seed"

    def test_seed_success_returns_row_counts(self, client, admin_headers):
        """Admin seed trigger returns a summary of generated rows."""
        with (
            patch(_ADMIN_REPO) as MockRepo,
            patch("seed.generator.run_seed", return_value={"users": 10, "matches": 5}),
        ):
            repo = MockRepo.return_value
            repo.conn = MagicMock()

            resp = client.post(
                self.ENDPOINT,
                headers={**admin_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_seed_requires_admin_role(self, client, parent_headers):
        """Non-admin callers receive 403 without touching the seed generator."""
        resp = client.post(
            self.ENDPOINT,
            headers={**parent_headers, "X-CSRF-Token": _CSRF},
            cookies={"csrf_token": _CSRF},
        )
        assert resp.status_code == 403


# ━━━━━━━━━━ Admin read endpoint ACL (SEC-13) ━━━━━━━━━━

class TestAdminReadACL:
    """Non-admin callers must receive 403 on all admin read endpoints."""

    def test_tables_requires_admin(self, client, parent_headers):
        """GET /api/admin/tables is admin-only; parent role returns 403."""
        resp = client.get("/api/admin/tables", headers=parent_headers)
        assert resp.status_code == 403

    def test_users_list_requires_admin(self, client, parent_headers):
        """GET /api/admin/users is admin-only; parent role returns 403."""
        resp = client.get("/api/admin/users", headers=parent_headers)
        assert resp.status_code == 403

    def test_system_status_requires_admin(self, client, parent_headers):
        """GET /api/admin/system-status is admin-only; parent role returns 403."""
        resp = client.get("/api/admin/system-status", headers=parent_headers)
        assert resp.status_code == 403


# ━━━━━━━━━━ Admin task status — no-pickle invariant (SEC-14) ━━━━━━━━━━

class TestAdminGetTask:
    ENDPOINT = "/api/admin/tasks/{task_id}"

    def test_task_requires_admin(self, client, parent_headers):
        """Non-admin callers receive 403 before any Huey storage is accessed."""
        resp = client.get(
            self.ENDPOINT.format(task_id="abc123"),
            headers=parent_headers,
        )
        assert resp.status_code == 403

    def test_task_pending_when_empty(self, client, admin_headers):
        """When Huey has no result yet the endpoint returns pending status."""
        with patch("app.worker.huey") as mock_huey:
            empty = object()
            mock_huey.EmptyData = empty
            mock_huey.storage.peek_data.return_value = empty

            resp = client.get(
                self.ENDPOINT.format(task_id="task-pending"),
                headers=admin_headers,
            )

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "pending"

    def test_task_completed_json_result_returned(self, client, admin_headers):
        """A completed task with a valid JSON payload is returned as completed status."""
        with patch("app.worker.huey") as mock_huey:
            empty = object()
            mock_huey.EmptyData = empty
            mock_huey.storage.peek_data.return_value = json.dumps({"count": 5}).encode()

            resp = client.get(
                self.ENDPOINT.format(task_id="task-done"),
                headers=admin_headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["status"] == "completed"
        assert body["data"]["result"]["count"] == 5

    def test_non_json_payload_refused_without_pickle(self, client, admin_headers):
        """Non-JSON bytes (e.g. pickle) must not be deserialized; endpoint returns corrupted status.

        CWE-502: deserializing untrusted pickle bytes is a remote-code-execution primitive.
        The endpoint must refuse the payload, return success=False, and never call pickle.loads.
        """
        with patch("app.worker.huey") as mock_huey:
            empty = object()
            mock_huey.EmptyData = empty
            # Pickle magic bytes — valid pickle preamble but not valid JSON.
            mock_huey.storage.peek_data.return_value = b"\x80\x04\x95"

            resp = client.get(
                self.ENDPOINT.format(task_id="task-corrupt"),
                headers=admin_headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["data"]["status"] == "corrupted"
