"""Analytics router tests: income, expense, and student-progress stats.

StatsAppService is patched at its construction site in
app.analytics.api.dependencies. Role-based access control is the main
invariant being tested — the service layer is mocked away entirely.
"""

from unittest.mock import MagicMock, patch

_STATS_SERVICE = "app.analytics.api.dependencies.StatsAppService"
_INCOME_TASK = "app.tasks.stats_tasks.calculate_income_stats"
_EXPENSE_TASK = "app.tasks.stats_tasks.calculate_expense_stats"


def _mock_task(task_id: str = "test-task-id-abc") -> MagicMock:
    result = MagicMock()
    result.id = task_id
    return result


class TestIncomeStats:
    ENDPOINT = "/api/stats/income"

    def test_tutor_can_query_own_income(self, client, tutor_headers, mock_conn):
        """Tutor receives a background task_id for their income statistics."""
        with patch(_INCOME_TASK, return_value=_mock_task("income-task-1")) as mock_task:
            resp = client.get(self.ENDPOINT, headers=tutor_headers)
            mock_task.assert_called_once()

        assert resp.status_code == 200
        assert resp.json()["data"]["task_id"] == "income-task-1"

    def test_parent_cannot_query_income(self, client, parent_headers, mock_conn):
        """Income stats require tutor role."""
        resp = client.get(self.ENDPOINT, headers=parent_headers)
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, client):
        resp = client.get(self.ENDPOINT)
        assert resp.status_code == 401

    def test_explicit_month_query_param_is_accepted(self, client, tutor_headers, mock_conn):
        """Passing month=YYYY-MM is validated and forwarded to the background task."""
        with patch(_INCOME_TASK, return_value=_mock_task()) as mock_task:
            resp = client.get(f"{self.ENDPOINT}?month=2026-01", headers=tutor_headers)
            mock_task.assert_called_once()

        assert resp.status_code == 200
        assert "task_id" in resp.json()["data"]


class TestExpenseStats:
    ENDPOINT = "/api/stats/expense"

    def test_parent_can_query_own_expenses(self, client, parent_headers, mock_conn):
        """Parent receives a background task_id for their spending statistics."""
        with patch(_EXPENSE_TASK, return_value=_mock_task("expense-task-1")) as mock_task:
            resp = client.get(self.ENDPOINT, headers=parent_headers)
            mock_task.assert_called_once()

        assert resp.status_code == 200
        assert resp.json()["data"]["task_id"] == "expense-task-1"

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
