"""Auth token lifecycle: POST /api/auth/refresh and POST /api/auth/logout.

Tests JTI blacklisting on refresh and token invalidation on logout.
Both endpoints require CSRF double-submit (not in _CSRF_EXEMPT_PATHS).
"""

from unittest.mock import patch

from app.shared.infrastructure.security import create_refresh_token


_USER_REPO = "app.identity.infrastructure.postgres_user_repo.PostgresUserRepository"
_SECURITY = "app.shared.infrastructure.security"

_CSRF = "test-csrf-token"


class TestRefreshToken:
    ENDPOINT = "/api/auth/refresh"

    def test_refresh_success_issues_new_tokens(self, client, mock_conn):
        """Valid refresh token cookie rotates to a fresh token pair."""
        refresh_tok = create_refresh_token({"sub": "1", "role": "parent"})
        with (
            patch(_USER_REPO) as MockRepo,
            patch(f"{_SECURITY}.is_refresh_token_blacklisted", return_value=False),
            patch(f"{_SECURITY}._is_token_revoked_for_user", return_value=False),
            patch("app.identity.domain.services.invalidate_refresh_token"),
        ):
            MockRepo.return_value.find_by_id.return_value = {
                "user_id": 1, "role": "parent", "display_name": "王媽媽",
            }
            resp = client.post(
                self.ENDPOINT,
                cookies={"refresh_token": refresh_tok, "csrf_token": _CSRF},
                headers={"X-CSRF-Token": _CSRF},
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["role"] == "parent"
        assert data["user_id"] == 1

    def test_refresh_missing_cookie_returns_401(self, client):
        """Request without a refresh_token cookie is rejected before token decode."""
        resp = client.post(
            self.ENDPOINT,
            cookies={"csrf_token": _CSRF},
            headers={"X-CSRF-Token": _CSRF},
        )
        assert resp.status_code == 401

    def test_refresh_malformed_token_returns_401(self, client):
        """A token that fails JWT decode is rejected."""
        resp = client.post(
            self.ENDPOINT,
            cookies={"refresh_token": "not.a.valid.jwt", "csrf_token": _CSRF},
            headers={"X-CSRF-Token": _CSRF},
        )
        assert resp.status_code == 401

    def test_refresh_blacklisted_jti_returns_401(self, client):
        """A previously invalidated (blacklisted) JTI cannot mint a new token pair."""
        refresh_tok = create_refresh_token({"sub": "1", "role": "parent"})
        with patch(f"{_SECURITY}.is_refresh_token_blacklisted", return_value=True):
            resp = client.post(
                self.ENDPOINT,
                cookies={"refresh_token": refresh_tok, "csrf_token": _CSRF},
                headers={"X-CSRF-Token": _CSRF},
            )
        assert resp.status_code == 401

    def test_refresh_consumes_jti_on_success(self, client, mock_conn):
        """On a successful refresh the old JTI is invalidated exactly once."""
        refresh_tok = create_refresh_token({"sub": "1", "role": "parent"})
        with (
            patch(_USER_REPO) as MockRepo,
            patch(f"{_SECURITY}.is_refresh_token_blacklisted", return_value=False),
            patch(f"{_SECURITY}._is_token_revoked_for_user", return_value=False),
            patch("app.identity.domain.services.invalidate_refresh_token") as mock_inv,
        ):
            MockRepo.return_value.find_by_id.return_value = {
                "user_id": 1, "role": "parent", "display_name": "陳老師",
            }
            client.post(
                self.ENDPOINT,
                cookies={"refresh_token": refresh_tok, "csrf_token": _CSRF},
                headers={"X-CSRF-Token": _CSRF},
            )

        mock_inv.assert_called_once()


class TestLogout:
    ENDPOINT = "/api/auth/logout"

    def test_logout_success_invalidates_jti(self, client, parent_headers):
        """Valid logout call blacklists the refresh token JTI exactly once."""
        refresh_tok = create_refresh_token({"sub": "1", "role": "parent"})
        with (
            patch(f"{_SECURITY}.decode_refresh_token") as mock_decode,
            patch(f"{_SECURITY}.invalidate_refresh_token") as mock_inv,
        ):
            mock_decode.return_value = {"sub": "1", "jti": "logout-jti-abc"}
            resp = client.post(
                self.ENDPOINT,
                headers={**parent_headers, "X-CSRF-Token": _CSRF},
                cookies={"refresh_token": refresh_tok, "csrf_token": _CSRF},
            )

        assert resp.status_code == 200
        mock_inv.assert_called_once_with("logout-jti-abc")

    def test_logout_missing_refresh_cookie_returns_400(self, client, parent_headers):
        """Logout without a refresh_token cookie is rejected before invalidation."""
        resp = client.post(
            self.ENDPOINT,
            headers={**parent_headers, "X-CSRF-Token": _CSRF},
            cookies={"csrf_token": _CSRF},
        )
        assert resp.status_code == 400

    def test_logout_requires_valid_access_token(self, client):
        """Unauthenticated logout is rejected at the get_current_user dependency."""
        resp = client.post(
            self.ENDPOINT,
            cookies={"csrf_token": _CSRF},
            headers={"X-CSRF-Token": _CSRF},
        )
        assert resp.status_code == 401

    def test_logout_rejects_mismatched_refresh_sub(self, client, parent_headers):
        """A refresh token whose sub differs from the access token sub is rejected."""
        refresh_tok = create_refresh_token({"sub": "99", "role": "tutor"})
        with patch(f"{_SECURITY}.decode_refresh_token") as mock_decode:
            mock_decode.return_value = {"sub": "99", "jti": "other-jti"}
            resp = client.post(
                self.ENDPOINT,
                headers={**parent_headers, "X-CSRF-Token": _CSRF},
                cookies={"refresh_token": refresh_tok, "csrf_token": _CSRF},
            )
        assert resp.status_code == 400
