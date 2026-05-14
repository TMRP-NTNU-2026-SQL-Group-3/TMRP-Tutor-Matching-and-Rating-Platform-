"""Middleware regression tests (I-13).

Verifies that rate-limit and CSRF middleware cannot be silently removed or
broken without at least one test failing.

Rate-limit: overrides the global True-returning patch with a False-returning
one so RateLimitMiddleware returns 429.

CSRF: sends mutating requests to a non-exempt path without the required
double-submit token and asserts 403.
"""

import pytest
from unittest.mock import MagicMock, call, patch


class TestRateLimitMiddleware:
    def test_exhausted_bucket_returns_429(self, client):
        """When the per-path/IP bucket is full the middleware returns 429 with Retry-After."""
        with patch("app.middleware.rate_limit.check_and_record_bucket", return_value=False):
            resp = client.get("/health")

        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    def test_allowed_bucket_passes_through(self, client):
        """When the bucket allows the request the handler is reached (not short-circuited)."""
        # The global conftest patch already returns True, so a normal GET to
        # /health should reach the handler and return 200 or 503 (DB not up),
        # but never 429.
        resp = client.get("/health")
        assert resp.status_code != 429


class TestCSRFMiddleware:
    def test_mutating_request_without_csrf_token_returns_403(self, client):
        """/api/auth/refresh (POST) is not CSRF-exempt; missing token → 403."""
        resp = client.post("/api/auth/refresh")
        assert resp.status_code == 403
        assert "CSRF" in resp.json()["message"]

    def test_csrf_cookie_header_mismatch_returns_403(self, client):
        """Cookie and header values that differ trigger the double-submit failure."""
        resp = client.post(
            "/api/auth/refresh",
            cookies={"csrf_token": "value-a"},
            headers={"X-CSRF-Token": "value-b"},
        )
        assert resp.status_code == 403
        assert "CSRF" in resp.json()["message"]

    def test_matching_csrf_token_passes_to_handler(self, client):
        """When cookie == header the CSRF check passes and the request reaches the handler.

        /api/auth/refresh with a valid CSRF pair but no refresh_token cookie
        returns 401 (handler logic), not 403 (middleware).
        """
        tok = "matching-csrf-value"
        resp = client.post(
            "/api/auth/refresh",
            cookies={"csrf_token": tok},
            headers={"X-CSRF-Token": tok},
        )
        assert resp.status_code == 401

    def test_safe_method_skips_csrf_check(self, client):
        """GET requests bypass CSRF validation regardless of token presence."""
        resp = client.get("/health")
        assert resp.status_code != 403

    def test_exempt_path_skips_csrf_check(self, client):
        """POST /api/auth/login is in _CSRF_EXEMPT_PATHS; missing token is allowed."""
        resp = client.post(
            "/api/auth/login",
            json={"username": "x", "password": "y"},
        )
        # May return 400/422 for bad credentials/schema, but never 403 from CSRF.
        assert resp.status_code != 403


class TestCheckAndRecordBucket:
    """SEC-22: unit tests for check_and_record_bucket logic.

    The conftest permanently patches check_and_record_bucket to True so the
    test suite can run without a live DB. These tests temporarily restore the
    real function (via the conftest patcher's saved original) so the counting,
    inserting, and fail-closed logic can be verified with a mocked pool.
    """

    @pytest.fixture(autouse=True)
    def restore_real_fn(self):
        """Stop the conftest patcher for check_and_record_bucket during this test."""
        import conftest as _conftest
        patcher = next(
            p for p in _conftest._lifespan_patchers
            if getattr(p, "attribute", "") == "check_and_record_bucket"
        )
        patcher.stop()
        yield
        patcher.start()

    def _make_pool(self, current_count: int):
        """Return a fake pool whose cursor returns current_count for the SELECT."""
        cur = MagicMock()
        # First execute: advisory lock (no return value used).
        # Second execute: SELECT COUNT(*) — fetchone returns the count.
        # Third execute: INSERT.
        cur.fetchone.return_value = (current_count,)
        conn = MagicMock()
        conn.cursor.return_value.__enter__ = lambda s: cur
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        pool = MagicMock()
        pool.getconn.return_value = conn
        return pool, conn, cur

    def test_below_limit_allows_and_inserts(self):
        from app.middleware.rate_limit import check_and_record_bucket

        pool, conn, cur = self._make_pool(current_count=3)
        with patch("app.shared.infrastructure.database._require_pool", return_value=pool):
            result = check_and_record_bucket("test|127.0.0.1", max_attempts=5, window_seconds=60)

        assert result is True
        # INSERT must have been called once.
        insert_calls = [c for c in cur.execute.call_args_list if "INSERT" in str(c)]
        assert len(insert_calls) == 1
        conn.commit.assert_called_once()
        pool.putconn.assert_called_once_with(conn)

    def test_at_limit_denies_and_does_not_insert(self):
        from app.middleware.rate_limit import check_and_record_bucket

        pool, conn, cur = self._make_pool(current_count=5)
        with patch("app.shared.infrastructure.database._require_pool", return_value=pool):
            result = check_and_record_bucket("test|127.0.0.1", max_attempts=5, window_seconds=60)

        assert result is False
        insert_calls = [c for c in cur.execute.call_args_list if "INSERT" in str(c)]
        assert len(insert_calls) == 0
        conn.rollback.assert_called_once()
        pool.putconn.assert_called_once_with(conn)

    def test_db_error_fail_open_by_default(self):
        from app.middleware.rate_limit import check_and_record_bucket

        pool = MagicMock()
        pool.getconn.side_effect = RuntimeError("db unavailable")
        with patch("app.shared.infrastructure.database._require_pool", return_value=pool):
            result = check_and_record_bucket("test|127.0.0.1", max_attempts=5, window_seconds=60)

        assert result is True

    def test_db_error_fail_closed_when_requested(self):
        from app.middleware.rate_limit import check_and_record_bucket

        pool = MagicMock()
        pool.getconn.side_effect = RuntimeError("db unavailable")
        with patch("app.shared.infrastructure.database._require_pool", return_value=pool):
            result = check_and_record_bucket(
                "login|127.0.0.1", max_attempts=10, window_seconds=60, fail_closed=True
            )

        assert result is False


class TestCSRFExemptPathsInvariant:
    def test_exempt_set_has_not_grown(self):
        """_CSRF_EXEMPT_PATHS must contain exactly the two pre-authentication paths.

        Adding any path to this set silently removes CSRF protection for it.
        Any change to this set must be a deliberate, reviewed security decision.
        """
        from app.middleware.csrf import _CSRF_EXEMPT_PATHS
        assert _CSRF_EXEMPT_PATHS == frozenset({"/api/auth/login", "/api/auth/register"})
