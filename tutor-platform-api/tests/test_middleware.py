"""Middleware regression tests (I-13).

Verifies that rate-limit and CSRF middleware cannot be silently removed or
broken without at least one test failing.

Rate-limit: overrides the global True-returning patch with a False-returning
one so RateLimitMiddleware returns 429.

CSRF: sends mutating requests to a non-exempt path without the required
double-submit token and asserts 403.
"""

from unittest.mock import patch


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
