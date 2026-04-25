"""Session API tests: create session / edit-log diff behaviour.

Patches the Teaching BC infrastructure repo (`PostgresSessionRepository`)
at its import site inside `app.teaching.api.session_router`.
"""

from unittest.mock import patch


_REPO_PATH = "app.teaching.api.session_router.PostgresSessionRepository"


def _edit_log_insert_calls(repo) -> list:
    """Return the calls to repo.insert_edit_log()."""
    return list(repo.insert_edit_log.call_args_list)


# ━━━━━━━━━━ Create session ━━━━━━━━━━

class TestCreateSession:
    ENDPOINT = "/api/sessions"

    def test_create_success(self, client, tutor_headers, mock_conn):
        """Tutor creates a session record successfully."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = {
                "match_id": 1, "status": "active", "tutor_user_id": 2,
            }
            repo.create.return_value = 50

            resp = client.post(self.ENDPOINT, json={
                "match_id": 1,
                "session_date": "2025-04-01T14:00:00",
                "hours": 2.0,
                "content_summary": "複習第三章",
            }, headers=tutor_headers)

        assert resp.status_code == 200
        assert resp.json()["data"]["session_id"] == 50

    def test_create_trial_match_allowed(self, client, tutor_headers, mock_conn):
        """Trial-status match allows session creation."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = {
                "match_id": 1, "status": "trial", "tutor_user_id": 2,
            }
            repo.create.return_value = 51

            resp = client.post(self.ENDPOINT, json={
                "match_id": 1,
                "session_date": "2025-04-01T14:00:00",
                "hours": 1.5,
                "content_summary": "試教數學",
            }, headers=tutor_headers)

        assert resp.status_code == 200

    def test_create_paused_match_denied(self, client, tutor_headers, mock_conn):
        """Paused match cannot accept new sessions."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = {
                "match_id": 1, "status": "paused", "tutor_user_id": 2,
            }

            resp = client.post(self.ENDPOINT, json={
                "match_id": 1,
                "session_date": "2025-04-01T14:00:00",
                "hours": 2.0,
                "content_summary": "暫停中",
            }, headers=tutor_headers)

        assert resp.status_code == 400
        assert "進行中" in resp.json()["message"]

    def test_parent_cannot_create(self, client, parent_headers, mock_conn):
        """Parent cannot create session records (403)."""
        resp = client.post(self.ENDPOINT, json={
            "match_id": 1,
            "session_date": "2025-04-01T14:00:00",
            "hours": 2.0,
            "content_summary": "test",
        }, headers=parent_headers)
        assert resp.status_code == 403

    def test_wrong_tutor_denied(self, client, tutor_headers, mock_conn):
        """Tutor not assigned to this match is denied."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = {
                "match_id": 1, "status": "active", "tutor_user_id": 999,
            }

            resp = client.post(self.ENDPOINT, json={
                "match_id": 1,
                "session_date": "2025-04-01T14:00:00",
                "hours": 2.0,
                "content_summary": "不是我的課",
            }, headers=tutor_headers)

        assert resp.status_code == 403


# ━━━━━━━━━━ Edit triggers edit-log ━━━━━━━━━━

class TestUpdateSession:
    ENDPOINT = "/api/sessions/{session_id}"

    def test_update_triggers_edit_log(self, client, tutor_headers, mock_conn):
        """Editing a session writes one edit-log row per changed field."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            old_session = {
                "session_id": 50,
                "match_id": 1,
                "hours": 2.0,
                "content_summary": "舊內容",
                "homework": None,
                "student_performance": None,
                "next_plan": None,
                "visible_to_parent": False,
            }
            repo.get_by_id.return_value = old_session
            repo.get_match_for_create.return_value = {
                "match_id": 1, "status": "active", "tutor_user_id": 2,
            }
            repo.fetch_one.return_value = old_session

            resp = client.put(
                self.ENDPOINT.format(session_id=50),
                json={"content_summary": "新內容", "hours": 3.0},
                headers=tutor_headers,
            )

        assert resp.status_code == 200
        log_calls = _edit_log_insert_calls(repo)
        assert len(log_calls) == 2
        logged_fields = {c.args[1] for c in log_calls}
        assert logged_fields == {"content_summary", "hours"}

    def test_update_no_diff_no_log(self, client, tutor_headers, mock_conn):
        """Sending the same values writes no edit-log rows."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            old_session = {
                "session_id": 50,
                "match_id": 1,
                "hours": 2.0,
                "content_summary": "原內容",
                "homework": None,
                "student_performance": None,
                "next_plan": None,
                "visible_to_parent": False,
            }
            repo.get_by_id.return_value = old_session
            repo.get_match_for_create.return_value = {
                "match_id": 1, "status": "active", "tutor_user_id": 2,
            }
            repo.fetch_one.return_value = old_session

            resp = client.put(
                self.ENDPOINT.format(session_id=50),
                json={"content_summary": "原內容", "hours": 2.0},
                headers=tutor_headers,
            )

        assert resp.status_code == 200
        assert "無實際變動" in resp.json()["message"]
        assert _edit_log_insert_calls(repo) == []

    def test_update_not_tutor_denied(self, client, parent_headers, mock_conn):
        """Parent cannot modify session records."""
        resp = client.put(
            self.ENDPOINT.format(session_id=50),
            json={"content_summary": "hacked"},
            headers=parent_headers,
        )
        assert resp.status_code == 403


# ━━━━━━━━━━ List sessions ━━━━━━━━━━

class TestListSessions:
    ENDPOINT = "/api/sessions"

    def test_list_as_tutor(self, client, tutor_headers, mock_conn):
        """Tutor lists all sessions for the match."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_participants.return_value = {
                "match_id": 1, "tutor_user_id": 2, "parent_user_id": 1,
            }
            repo.list_by_match.return_value = [
                {"session_id": 50, "visible_to_parent": True},
                {"session_id": 51, "visible_to_parent": False},
            ]

            resp = client.get(
                self.ENDPOINT, params={"match_id": 1},
                headers=tutor_headers,
            )

        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2
        repo.list_by_match.assert_called_once_with(1, visible_only=False)

    def test_list_as_parent_filtered(self, client, parent_headers, mock_conn):
        """Parent sees only visible_to_parent=true rows."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_participants.return_value = {
                "match_id": 1, "tutor_user_id": 2, "parent_user_id": 1,
            }
            repo.list_by_match.return_value = [
                {"session_id": 50, "visible_to_parent": True},
            ]

            resp = client.get(
                self.ENDPOINT, params={"match_id": 1},
                headers=parent_headers,
            )

        assert resp.status_code == 200
        repo.list_by_match.assert_called_once_with(1, visible_only=True)


# ━━━━━━━━━━ Edit-log retrieval ━━━━━━━━━━

class TestEditLogs:
    ENDPOINT = "/api/sessions/{session_id}/edit-logs"

    def test_get_edit_logs_success(self, client, tutor_headers, mock_conn):
        """Tutor can view edit history."""
        with patch(_REPO_PATH) as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id.return_value = {"session_id": 50, "match_id": 1}
            repo.get_match_participants.return_value = {
                "match_id": 1, "tutor_user_id": 2, "parent_user_id": 1,
            }
            repo.get_edit_logs.return_value = [
                {
                    "session_id": 50,
                    "field_name": "hours",
                    "old_value": "2.0",
                    "new_value": "3.0",
                    "edited_at": "2025-04-01T15:00:00",
                },
            ]

            resp = client.get(
                self.ENDPOINT.format(session_id=50),
                headers=tutor_headers,
            )

        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1
