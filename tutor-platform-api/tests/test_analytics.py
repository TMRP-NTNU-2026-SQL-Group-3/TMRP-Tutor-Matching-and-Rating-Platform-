"""Analytics router tests: income, expense, and student-progress stats.

StatsAppService is patched at its construction site in
app.analytics.api.dependencies. Role-based access control is the main
invariant being tested — the service layer is mocked away entirely.
"""

from unittest.mock import patch

_STATS_SERVICE = "app.analytics.api.dependencies.StatsAppService"


class TestIncomeStats:
    ENDPOINT = "/api/stats/income"

    def test_tutor_can_query_own_income(self, client, tutor_headers, mock_conn):
        """Tutor receives their income statistics for the current month."""
        with patch(_STATS_SERVICE) as MockService:
            MockService.return_value.income_stats.return_value = {
                "total_income": 12000,
                "sessions": 4,
            }

            resp = client.get(self.ENDPOINT, headers=tutor_headers)

        assert resp.status_code == 200
        assert resp.json()["data"]["total_income"] == 12000

    def test_parent_cannot_query_income(self, client, parent_headers, mock_conn):
        """Income stats require tutor role."""
        resp = client.get(self.ENDPOINT, headers=parent_headers)
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, client):
        resp = client.get(self.ENDPOINT)
        assert resp.status_code == 401

    def test_explicit_month_query_param_is_accepted(self, client, tutor_headers, mock_conn):
        """Passing month=YYYY-MM selects a historical period."""
        with patch(_STATS_SERVICE) as MockService:
            MockService.return_value.income_stats.return_value = {"total_income": 0, "sessions": 0}

            resp = client.get(f"{self.ENDPOINT}?month=2026-01", headers=tutor_headers)

        assert resp.status_code == 200


class TestExpenseStats:
    ENDPOINT = "/api/stats/expense"

    def test_parent_can_query_own_expenses(self, client, parent_headers, mock_conn):
        """Parent receives their spending statistics for the current month."""
        with patch(_STATS_SERVICE) as MockService:
            MockService.return_value.expense_stats.return_value = {
                "total_expense": 8000,
                "sessions": 3,
            }

            resp = client.get(self.ENDPOINT, headers=parent_headers)

        assert resp.status_code == 200
        assert resp.json()["data"]["total_expense"] == 8000

    def test_tutor_cannot_query_expense(self, client, tutor_headers, mock_conn):
        """Expense stats require parent role."""
        resp = client.get(self.ENDPOINT, headers=tutor_headers)
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, client):
        resp = client.get(self.ENDPOINT)
        assert resp.status_code == 401


class TestStudentProgress:
    def test_parent_can_view_student_progress(self, client, parent_headers, mock_conn):
        """Parent with student ownership can view the exam score trend."""
        with patch(_STATS_SERVICE) as MockService:
            MockService.return_value.student_progress.return_value = {
                "student_id": 1,
                "exams": [],
            }

            resp = client.get("/api/stats/student-progress/1", headers=parent_headers)

        assert resp.status_code == 200
        assert resp.json()["data"]["student_id"] == 1

    def test_tutor_is_blocked_by_route_guard(self, client, tutor_headers, mock_conn):
        """Route-level guard rejects tutor role before any service call (spec §7.7)."""
        resp = client.get("/api/stats/student-progress/1", headers=tutor_headers)
        assert resp.status_code == 403

    def test_admin_can_view_student_progress(self, client, admin_headers, mock_conn):
        """Admins bypass the ownership check and may view any student's progress."""
        with patch(_STATS_SERVICE) as MockService:
            MockService.return_value.student_progress.return_value = {
                "student_id": 1,
                "exams": [],
            }

            resp = client.get("/api/stats/student-progress/1", headers=admin_headers)

        assert resp.status_code == 200

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/api/stats/student-progress/1")
        assert resp.status_code == 401
