"""Auth API 測試：註冊 / 登入 / Token 驗證。"""

from unittest.mock import patch

from app.utils.security import hash_password


# ━━━━━━━━━━ 註冊 ━━━━━━━━━━

class TestRegister:
    ENDPOINT = "/api/auth/register"

    def test_register_parent_success(self, client, mock_conn):
        """家長註冊成功，回傳 user_id。"""
        with patch("app.routers.auth.AuthRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_username.return_value = None
            repo.register_user.return_value = 10

            resp = client.post(self.ENDPOINT, json={
                "username": "parent01",
                "password": "Secure123",
                "display_name": "王媽媽",
                "role": "parent",
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["user_id"] == 10

    def test_register_tutor_success(self, client, mock_conn):
        """家教註冊成功。"""
        with patch("app.routers.auth.AuthRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_username.return_value = None
            repo.register_user.return_value = 11

            resp = client.post(self.ENDPOINT, json={
                "username": "tutor01",
                "password": "Secure456",
                "display_name": "陳老師",
                "role": "tutor",
            })

        assert resp.status_code == 200
        assert resp.json()["data"]["user_id"] == 11

    def test_register_duplicate_username(self, client, mock_conn):
        """重複帳號回傳 400。"""
        with patch("app.routers.auth.AuthRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_username.return_value = {"user_id": 1}

            resp = client.post(self.ENDPOINT, json={
                "username": "existed",
                "password": "pass",
                "display_name": "重複",
                "role": "parent",
            })

        assert resp.status_code == 400
        assert "帳號已存在" in resp.json()["message"]

    def test_register_invalid_role(self, client, mock_conn):
        """無效角色回傳 400。"""
        with patch("app.routers.auth.AuthRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_username.return_value = None

            resp = client.post(self.ENDPOINT, json={
                "username": "bad_role",
                "password": "pass",
                "display_name": "壞角色",
                "role": "admin",
            })

        assert resp.status_code == 400
        assert "角色" in resp.json()["message"]


# ━━━━━━━━━━ 登入 ━━━━━━━━━━

class TestLogin:
    ENDPOINT = "/api/auth/login"

    def test_login_success(self, client, mock_conn):
        """正確帳密取得 Token。"""
        hashed = hash_password("correct_pw")
        with patch("app.routers.auth.AuthRepository") as MockRepo:
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
        assert "access_token" in data
        assert data["role"] == "parent"

    def test_login_wrong_password(self, client, mock_conn):
        """密碼錯誤回傳 400。"""
        hashed = hash_password("correct_pw")
        with patch("app.routers.auth.AuthRepository") as MockRepo:
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
        """帳號不存在回傳 400。"""
        with patch("app.routers.auth.AuthRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_username.return_value = None

            resp = client.post(self.ENDPOINT, json={
                "username": "ghost",
                "password": "any",
            })

        assert resp.status_code == 400


# ━━━━━━━━━━ Token 驗證 ━━━━━━━━━━

class TestGetMe:
    ENDPOINT = "/api/auth/me"

    def test_get_me_success(self, client, parent_headers, mock_conn):
        """帶有效 Token 取得個人資訊。"""
        with patch("app.routers.auth.AuthRepository") as MockRepo:
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
        """未帶 Token 回傳 401。"""
        resp = client.get(self.ENDPOINT)
        assert resp.status_code == 401

    def test_get_me_invalid_token(self, client):
        """無效 Token 回傳 401。"""
        resp = client.get(
            self.ENDPOINT,
            headers={"Authorization": "Bearer invalid.jwt.token"},
        )
        assert resp.status_code == 401
