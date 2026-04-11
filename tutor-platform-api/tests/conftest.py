"""
共用 Fixtures：提供 TestClient、假使用者 Token、Mock DB 連線。

測試策略：
    以 unittest.mock 攔截 repository 方法，不依賴實際資料庫連線，
    確保測試可在任何環境中快速、獨立地執行。
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.utils.security import create_access_token


# ── Mock DB 連線 ──────────────────────────────────────────────
@pytest.fixture()
def mock_conn():
    """回傳一個 MagicMock 作為 psycopg2 Connection 替身。"""
    conn = MagicMock()
    conn.cursor.return_value = MagicMock()
    return conn


@pytest.fixture(autouse=True)
def _reset_overrides():
    """確保每個測試前後清除依賴覆蓋，避免跨測試污染。"""
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def client(mock_conn):
    """使用 mock_conn 覆蓋 get_db 依賴的 TestClient。"""
    def _get_mock_db():
        return mock_conn
    app.dependency_overrides[get_db] = _get_mock_db
    with TestClient(app) as c:
        yield c


# ── Token 工廠 ────────────────────────────────────────────────
def _make_token(user_id: int, role: str) -> str:
    return create_access_token({"sub": str(user_id), "role": role})


@pytest.fixture()
def parent_token():
    """家長 (user_id=1) 的有效 JWT Token。"""
    return _make_token(1, "parent")


@pytest.fixture()
def parent_headers(parent_token):
    return {"Authorization": f"Bearer {parent_token}"}


@pytest.fixture()
def tutor_token():
    """家教 (user_id=2) 的有效 JWT Token。"""
    return _make_token(2, "tutor")


@pytest.fixture()
def tutor_headers(tutor_token):
    return {"Authorization": f"Bearer {tutor_token}"}


@pytest.fixture()
def admin_token():
    """管理員 (user_id=99) 的有效 JWT Token。"""
    return _make_token(99, "admin")


@pytest.fixture()
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}
