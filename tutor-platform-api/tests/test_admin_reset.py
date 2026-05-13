"""Admin database reset flow tests (SEC-8).

The reset is a two-step operation:
  Step 1  POST /api/admin/reset          — issues a short-lived reset token
  Step 2  POST /api/admin/reset/confirm  — requires token + plaintext password

Mocking strategy for the confirm step:
  - decode_reset_confirmation_token / consume_reset_confirmation_jti /
    verify_password are patched at their import sites in app.admin.api.router.
  - AdminImportService is patched at its construction site in
    app.admin.api.dependencies so export_all_tables_to_zip and
    reset_database return controlled values.
  - The mock_conn's cursor MagicMock is truthy for the advisory-lock and
    password-hash cursor reads without additional setup.
"""

from unittest.mock import MagicMock, patch

_DECODE_TOKEN = "app.admin.api.router.decode_reset_confirmation_token"
_CONSUME_JTI = "app.admin.api.router.consume_reset_confirmation_jti"
_VERIFY_PW = "app.admin.api.router.verify_password"
_IMPORT_SERVICE = "app.admin.api.dependencies.AdminImportService"
_CSRF = "test-csrf-token"


def _confirm_headers(admin_headers):
    return {**admin_headers, "X-CSRF-Token": _CSRF}


def _confirm_cookies():
    return {"csrf_token": _CSRF}


class TestRequestReset:
    ENDPOINT = "/api/admin/reset"

    def test_admin_receives_reset_token(self, client, admin_headers, mock_conn):
        """Step 1 returns a reset_token and a 5-minute expiry hint."""
        resp = client.post(
            self.ENDPOINT,
            headers={**admin_headers, "X-CSRF-Token": _CSRF},
            cookies={"csrf_token": _CSRF},
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "reset_token" in data
        assert data["expires_in"] == 300

    def test_non_admin_cannot_request_reset(self, client, parent_headers, mock_conn):
        """Step 1 requires admin role."""
        resp = client.post(
            self.ENDPOINT,
            headers={**parent_headers, "X-CSRF-Token": _CSRF},
            cookies={"csrf_token": _CSRF},
        )
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, client):
        resp = client.post(
            self.ENDPOINT,
            headers={"X-CSRF-Token": _CSRF},
            cookies={"csrf_token": _CSRF},
        )
        assert resp.status_code == 401


class TestConfirmReset:
    ENDPOINT = "/api/admin/reset/confirm"

    def test_confirm_reset_success(self, client, admin_headers, mock_conn):
        """Valid token + correct password + advisory lock acquired triggers a reset."""
        with (
            patch(_DECODE_TOKEN, return_value={"sub": "99", "jti": "test-jti-1"}),
            patch(_CONSUME_JTI, return_value=True),
            patch(_VERIFY_PW, return_value=True),
            patch(_IMPORT_SERVICE) as MockService,
        ):
            svc = MockService.return_value
            svc.export_all_tables_to_zip.return_value = MagicMock()
            svc.reset_database.return_value = {"users": 0, "tutors": 0}

            resp = client.post(
                self.ENDPOINT,
                json={"reset_token": "valid-token", "password": "AdminPass123"},
                headers=_confirm_headers(admin_headers),
                cookies=_confirm_cookies(),
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "deleted" in data
        assert "backup_created" in data

    def test_invalid_reset_token_returns_401(self, client, admin_headers, mock_conn):
        """Token whose sub does not match the caller's user_id is rejected."""
        with (
            patch(_DECODE_TOKEN, return_value={"sub": "999", "jti": "mismatch-jti"}),
            patch(_IMPORT_SERVICE),
        ):
            resp = client.post(
                self.ENDPOINT,
                json={"reset_token": "bad-token", "password": "AdminPass123"},
                headers=_confirm_headers(admin_headers),
                cookies=_confirm_cookies(),
            )

        assert resp.status_code == 401

    def test_null_token_payload_returns_401(self, client, admin_headers, mock_conn):
        """Expired or tampered token returns None from decode and is rejected."""
        with (
            patch(_DECODE_TOKEN, return_value=None),
            patch(_IMPORT_SERVICE),
        ):
            resp = client.post(
                self.ENDPOINT,
                json={"reset_token": "expired-token", "password": "AdminPass123"},
                headers=_confirm_headers(admin_headers),
                cookies=_confirm_cookies(),
            )

        assert resp.status_code == 401

    def test_replayed_jti_returns_401(self, client, admin_headers, mock_conn):
        """JTI single-use enforcement: a second attempt with the same token is blocked."""
        with (
            patch(_DECODE_TOKEN, return_value={"sub": "99", "jti": "used-jti"}),
            patch(_CONSUME_JTI, return_value=False),
            patch(_IMPORT_SERVICE),
        ):
            resp = client.post(
                self.ENDPOINT,
                json={"reset_token": "used-token", "password": "AdminPass123"},
                headers=_confirm_headers(admin_headers),
                cookies=_confirm_cookies(),
            )

        assert resp.status_code == 401

    def test_wrong_password_returns_401(self, client, admin_headers, mock_conn):
        """Re-verification failure: wrong plaintext password is rejected."""
        with (
            patch(_DECODE_TOKEN, return_value={"sub": "99", "jti": "good-jti"}),
            patch(_CONSUME_JTI, return_value=True),
            patch(_VERIFY_PW, return_value=False),
            patch(_IMPORT_SERVICE),
        ):
            resp = client.post(
                self.ENDPOINT,
                json={"reset_token": "valid-token", "password": "WrongPassword1"},
                headers=_confirm_headers(admin_headers),
                cookies=_confirm_cookies(),
            )

        assert resp.status_code == 401

    def test_concurrent_lock_returns_409(self, client, admin_headers, mock_conn):
        """Advisory lock contention raises 409 so concurrent wipes are serialised."""
        mock_conn.cursor.return_value.__enter__.return_value.fetchone.return_value = [False]
        with (
            patch(_DECODE_TOKEN, return_value={"sub": "99", "jti": "lock-jti"}),
            patch(_IMPORT_SERVICE),
        ):
            resp = client.post(
                self.ENDPOINT,
                json={"reset_token": "valid-token", "password": "AdminPass123"},
                headers=_confirm_headers(admin_headers),
                cookies=_confirm_cookies(),
            )

        assert resp.status_code == 409

    def test_non_admin_cannot_confirm_reset(self, client, parent_headers, mock_conn):
        """Confirm step requires admin role."""
        resp = client.post(
            self.ENDPOINT,
            json={"reset_token": "any", "password": "AdminPass123"},
            headers={**parent_headers, "X-CSRF-Token": _CSRF},
            cookies={"csrf_token": _CSRF},
        )
        assert resp.status_code == 403
