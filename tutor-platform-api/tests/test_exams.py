"""Exam router tests: create, list, update, and delete exam records.

The exam router has two route prefixes:
  POST/GET /api/students/{student_id}/exams  (student_exams_router)
  PUT/DELETE /api/exams/{exam_id}            (exam_router)

ExamAppService is patched at its construction site in
app.teaching.api.dependencies. The service layer enforces ownership and
visibility; this test layer focuses on HTTP status codes and access control.
"""

from unittest.mock import patch

_EXAM_SERVICE = "app.teaching.api.dependencies.ExamAppService"
_CSRF = "test-csrf-token"

_VALID_EXAM_BODY = {
    "subject_id": 1,
    "exam_date": "2026-03-01T00:00:00",
    "exam_type": "段考",
    "score": 88.0,
}


class TestCreateExam:
    def test_tutor_can_create_exam_record(self, client, tutor_headers, mock_conn):
        """Authenticated tutor can add an exam record; service enforces ownership."""
        with patch(_EXAM_SERVICE) as MockService:
            MockService.return_value.create_exam.return_value = 7

            resp = client.post(
                "/api/students/1/exams",
                json=_VALID_EXAM_BODY,
                headers={**tutor_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 201
        assert resp.json()["data"]["exam_id"] == 7

    def test_parent_can_create_exam_record(self, client, parent_headers, mock_conn):
        """Authenticated parent can also add an exam record."""
        with patch(_EXAM_SERVICE) as MockService:
            MockService.return_value.create_exam.return_value = 8

            resp = client.post(
                "/api/students/1/exams",
                json=_VALID_EXAM_BODY,
                headers={**parent_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 201
        assert resp.json()["data"]["exam_id"] == 8

    def test_invalid_exam_type_returns_422(self, client, tutor_headers, mock_conn):
        """ExamType validator rejects values outside the allowed set."""
        resp = client.post(
            "/api/students/1/exams",
            json={**_VALID_EXAM_BODY, "exam_type": "invalid_type"},
            headers={**tutor_headers, "X-CSRF-Token": _CSRF},
            cookies={"csrf_token": _CSRF},
        )
        assert resp.status_code == 422

    def test_unauthenticated_returns_401(self, client):
        resp = client.post(
            "/api/students/1/exams",
            json=_VALID_EXAM_BODY,
            headers={"X-CSRF-Token": _CSRF},
            cookies={"csrf_token": _CSRF},
        )
        assert resp.status_code == 401


class TestListExams:
    def test_tutor_can_list_exams_for_student(self, client, tutor_headers, mock_conn):
        """Authenticated tutor lists exam records for a student they teach."""
        with patch(_EXAM_SERVICE) as MockService:
            MockService.return_value.list_exams.return_value = [
                {"exam_id": 1, "score": 90, "exam_type": "段考"},
                {"exam_id": 2, "score": 75, "exam_type": "小考"},
            ]

            resp = client.get("/api/students/1/exams", headers=tutor_headers)

        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    def test_parent_can_list_exams(self, client, parent_headers, mock_conn):
        """Parent can list exam records for their own student."""
        with patch(_EXAM_SERVICE) as MockService:
            MockService.return_value.list_exams.return_value = []

            resp = client.get("/api/students/1/exams", headers=parent_headers)

        assert resp.status_code == 200

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/api/students/1/exams")
        assert resp.status_code == 401


class TestDeleteExam:
    def test_creator_can_delete_exam(self, client, tutor_headers, mock_conn):
        """Exam creator can delete the record; service enforces authorship."""
        with patch(_EXAM_SERVICE) as MockService:
            MockService.return_value.delete_exam.return_value = None

            resp = client.delete(
                "/api/exams/1",
                headers={**tutor_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 200

    def test_unauthenticated_returns_401(self, client):
        resp = client.delete(
            "/api/exams/1",
            headers={"X-CSRF-Token": _CSRF},
            cookies={"csrf_token": _CSRF},
        )
        assert resp.status_code == 401


class TestUpdateExam:
    def test_creator_can_update_score(self, client, tutor_headers, mock_conn):
        """Exam creator can modify the score field."""
        with patch(_EXAM_SERVICE) as MockService:
            MockService.return_value.update_exam.return_value = None

            resp = client.put(
                "/api/exams/1",
                json={"score": 95.0},
                headers={**tutor_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 200

    def test_empty_body_is_no_op(self, client, tutor_headers, mock_conn):
        """An update body with no recognized fields returns 200 without a DB write."""
        with patch(_EXAM_SERVICE) as MockService:
            MockService.return_value.update_exam.return_value = None

            resp = client.put(
                "/api/exams/1",
                json={},
                headers={**tutor_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 200

    def test_score_out_of_range_returns_422(self, client, tutor_headers, mock_conn):
        """Score above 150 violates the Pydantic constraint."""
        resp = client.put(
            "/api/exams/1",
            json={"score": 200.0},
            headers={**tutor_headers, "X-CSRF-Token": _CSRF},
            cookies={"csrf_token": _CSRF},
        )
        assert resp.status_code == 422
