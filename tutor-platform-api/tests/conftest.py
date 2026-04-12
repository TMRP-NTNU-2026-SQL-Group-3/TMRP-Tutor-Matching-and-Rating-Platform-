"""Shared fixtures: TestClient, fake-user tokens, mock DB connection.

Strategy: intercept repository methods via unittest.mock so tests do not
depend on a real Postgres. The FastAPI lifespan (which otherwise tries to
open a connection pool on app startup) is patched to a no-op for the
duration of the test session.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# Patch the infrastructure module's functions BEFORE `app.main` imports them.
# Otherwise `app.main` has already captured bound references to the real
# init/seed helpers, and patching later has no effect during lifespan.
_lifespan_patchers = [
    patch("app.shared.infrastructure.database.init_pool", return_value=None),
    patch("app.shared.infrastructure.database.close_pool", return_value=None),
    patch("app.shared.infrastructure.database.get_connection", return_value=MagicMock()),
    patch("app.shared.infrastructure.database.release_connection", return_value=None),
    patch("app.init_db.create_schema", return_value=None),
    patch("app.init_db.seed_subjects", return_value=None),
    patch("app.init_db.ensure_admin_user", return_value=None),
    # Rate-limit middleware hits Postgres on every request; short-circuit it.
    patch("app.middleware.rate_limit._check_and_record", return_value=True),
    patch("app.middleware.rate_limit._cleanup_expired", return_value=0),
]
for p in _lifespan_patchers:
    p.start()

from app.main import app  # noqa: E402
from app.shared.infrastructure.database import get_db  # noqa: E402
from app.utils.security import create_access_token  # noqa: E402


# ── Mock DB connection ────────────────────────────────────────
@pytest.fixture()
def mock_conn():
    """A MagicMock standing in for a psycopg2 Connection."""
    conn = MagicMock()
    conn.cursor.return_value = MagicMock()
    return conn


@pytest.fixture(autouse=True)
def _reset_overrides():
    """Clear dependency overrides around each test to avoid cross-pollution."""
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def client(mock_conn):
    """TestClient with get_db overridden to return mock_conn."""
    def _get_mock_db():
        return mock_conn
    app.dependency_overrides[get_db] = _get_mock_db
    with TestClient(app) as c:
        yield c


# ── Token factory ─────────────────────────────────────────────
def _make_token(user_id: int, role: str) -> str:
    return create_access_token({"sub": str(user_id), "role": role})


@pytest.fixture()
def parent_token():
    """Valid JWT for parent (user_id=1)."""
    return _make_token(1, "parent")


@pytest.fixture()
def parent_headers(parent_token):
    return {"Authorization": f"Bearer {parent_token}"}


@pytest.fixture()
def tutor_token():
    """Valid JWT for tutor (user_id=2)."""
    return _make_token(2, "tutor")


@pytest.fixture()
def tutor_headers(tutor_token):
    return {"Authorization": f"Bearer {tutor_token}"}


@pytest.fixture()
def admin_token():
    """Valid JWT for admin (user_id=99)."""
    return _make_token(99, "admin")


@pytest.fixture()
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}
