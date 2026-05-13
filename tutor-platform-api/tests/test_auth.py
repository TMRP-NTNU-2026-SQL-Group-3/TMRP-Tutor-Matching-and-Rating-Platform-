"""Auth API tests: register / login / token verification.

Patches the Identity BC infrastructure repo (`PostgresUserRepository`) at its
source module (`app.identity.infrastructure.postgres_user_repo`) so the mock
intercepts the lazy import inside `get_auth_service` at call time.
"""

from unittest.mock import patch

from app.shared.infrastructure.security import hash_password


_REPO_PATH = "app.identity.infrastructure.postgres_user_repo.PostgresUserRepository"


# ━━━━━━━━━━ Register ━━━━━━━━━━

class TestRegister:
    ENDPOINT = "/api/auth/register"

    def test_register_parent_success(self, client, mock_conn):
        """Parent registration returns the new user_id."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_username.return_value = None
            repo.register_user.return_value = 10

            resp = client.post(self.ENDPOINT, json={
                "username": "parent01",
                "password": "Secure12345",
                "display_name": "王媽媽",
                "role": "parent",
            })

        assert resp.status_code == 201
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["user_id"] == 10

    def test_register_tutor_success(self, client, mock_conn):
        """Tutor registration succeeds."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_username.return_value = None
            repo.register_user.return_value = 11

            resp = client.post(self.ENDPOINT, json={
                "username": "tutor01",
                "password": "Secure45678",
                "display_name": "陳老師",
                "role": "tutor",
            })

        assert resp.status_code == 201
        assert resp.json()["data"]["user_id"] == 11

    def test_register_duplicate_username(self, client, mock_conn):
        """Duplicate username returns 409 Conflict."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_username.return_value = {"user_id": 1}

            resp = client.post(self.ENDPOINT, json={
                "username": "existed",
                "password": "Secure12345",
                "display_name": "重複",
                "role": "parent",
            })

        assert resp.status_code == 409
        assert "帳號已存在" in resp.json()["message"]

    def test_register_invalid_role(self, client, mock_conn):
        """Invalid role is rejected by schema validation (422)."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_username.return_value = None

            resp = client.post(self.ENDPOINT, json={
                "username": "bad_role",
                "password": "Secure12345",
                "display_name": "壞角色",
                "role": "admin",
            })

        # The Identity schema restricts role to Literal["parent", "tutor"],
        # so Pydantic returns 422 before the domain service sees the request.
        assert resp.status_code == 422


# ━━━━━━━━━━ Login ━━━━━━━━━━

class TestLogin:
    ENDPOINT = "/api/auth/login"

    def test_login_success(self, client, mock_conn):
        """Correct credentials return a token and deliver HttpOnly auth cookies."""
        hashed = hash_password("correct_pw")
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_username.return_value = {
                "user_id": 1,
                "username": "parent01",
                "password_hash": hashed,
                "role": "parent",
                "display_name": "王媽媽",
            }

            resp = client.post(self.ENDPOINT, json={
                "username": "parent01",
                "password": "correct_pw",
            })

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_id"] == 1
        assert data["role"] == "parent"

        # SEC-C02: verify cookie delivery with correct security flags
        set_cookie_headers = resp.headers.get_list("set-cookie")
        access_cookie = next((h for h in set_cookie_headers if "access_token" in h), None)
        refresh_cookie = next((h for h in set_cookie_headers if "refresh_token" in h), None)
        csrf_cookie = next((h for h in set_cookie_headers if "csrf_token" in h), None)
        assert access_cookie is not None, "access_token cookie not delivered"
        assert refresh_cookie is not None, "refresh_token cookie not delivered"
        assert csrf_cookie is not None, "csrf_token cookie not delivered"
        assert "httponly" in access_cookie.lower(), "access_token must be HttpOnly"
        assert "httponly" in refresh_cookie.lower(), "refresh_token must be HttpOnly"
        assert "httponly" not in csrf_cookie.lower(), "csrf_token must not be HttpOnly (SPA reads it)"
        assert "samesite=lax" in access_cookie.lower(), "access_token must have SameSite=Lax"
        assert "samesite=lax" in refresh_cookie.lower(), "refresh_token must have SameSite=Lax"

    def test_login_wrong_password(self, client, mock_conn):
        """Wrong password returns 400."""
        hashed = hash_password("correct_pw")
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_username.return_value = {
                "user_id": 1,
                "username": "parent01",
                "password_hash": hashed,
                "role": "parent",
                "display_name": "王媽媽",
            }

            resp = client.post(self.ENDPOINT, json={
                "username": "parent01",
                "password": "wrong_pw",
            })

        assert resp.status_code == 400
        assert "帳號或密碼錯誤" in resp.json()["message"]

    def test_login_user_not_found(self, client, mock_conn):
        """Missing user returns 400."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_username.return_value = None

            resp = client.post(self.ENDPOINT, json={
                "username": "ghost",
                "password": "any",
            })

        assert resp.status_code == 400


# ━━━━━━━━━━ Token verification ━━━━━━━━━━

class TestGetMe:
    ENDPOINT = "/api/auth/me"

    def test_get_me_success(self, client, parent_headers, mock_conn):
        """Valid token returns personal info (password hash stripped)."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_id.return_value = {
                "user_id": 1,
                "username": "parent01",
                "display_name": "王媽媽",
                "role": "parent",
                "password_hash": "xxx",
            }

            resp = client.get(self.ENDPOINT, headers=parent_headers)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["display_name"] == "王媽媽"
        assert "password_hash" not in data

    def test_get_me_no_token(self, client):
        """No token returns 401."""
        resp = client.get(self.ENDPOINT)
        assert resp.status_code == 401

    def test_get_me_invalid_token(self, client):
        """Invalid token returns 401."""
        resp = client.get(
            self.ENDPOINT,
            headers={"Authorization": "Bearer invalid.jwt.token"},
        )
        assert resp.status_code == 401
