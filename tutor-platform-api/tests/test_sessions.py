"""Session API 測試：建立課堂紀錄 / 修改觸發 edit log。"""

from unittest.mock import patch


# ━━━━━━━━━━ 建立課堂紀錄 ━━━━━━━━━━

class TestCreateSession:
    ENDPOINT = "/api/sessions"

    def test_create_success(self, client, tutor_headers, mock_conn):
        """老師建立上課日誌成功。"""
        with patch("app.routers.sessions.SessionRepository") as MockRepo:
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
        """試教中的配對也可以建立日誌。"""
        with patch("app.routers.sessions.SessionRepository") as MockRepo:
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
        """暫停中的配對無法建立日誌。"""
        with patch("app.routers.sessions.SessionRepository") as MockRepo:
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
        """家長不能建立上課日誌（403）。"""
        resp = client.post(self.ENDPOINT, json={
            "match_id": 1,
            "session_date": "2025-04-01T14:00:00",
            "hours": 2.0,
            "content_summary": "test",
        }, headers=parent_headers)
        assert resp.status_code == 403

    def test_wrong_tutor_denied(self, client, tutor_headers, mock_conn):
        """非配對中的老師不能建立日誌。"""
        with patch("app.routers.sessions.SessionRepository") as MockRepo:
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


# ━━━━━━━━━━ 修改觸發 Edit Log ━━━━━━━━━━

class TestUpdateSession:
    ENDPOINT = "/api/sessions/{session_id}"

    def test_update_triggers_edit_log(self, client, tutor_headers, mock_conn):
        """修改上課日誌時會寫入修改紀錄。"""
        with patch("app.routers.sessions.SessionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id.return_value = {
                "session_id": 50,
                "match_id": 1,
                "hours": 2.0,
                "content_summary": "舊內容",
                "homework": None,
                "student_performance": None,
                "next_plan": None,
                "visible_to_parent": False,
            }
            repo.get_match_for_create.return_value = {
                "match_id": 1, "status": "active", "tutor_user_id": 2,
            }

            resp = client.put(
                self.ENDPOINT.format(session_id=50),
                json={"content_summary": "新內容", "hours": 3.0},
                headers=tutor_headers,
            )

        assert resp.status_code == 200
        # 驗證 insert_edit_log 被呼叫了兩次（hours 和 content_summary）
        log_calls = repo.insert_edit_log.call_args_list
        assert len(log_calls) == 2
        logged_fields = {c.args[1] for c in log_calls}
        assert "content_summary" in logged_fields
        assert "hours" in logged_fields

    def test_update_no_diff_no_log(self, client, tutor_headers, mock_conn):
        """送相同的值不會產生修改紀錄。"""
        with patch("app.routers.sessions.SessionRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_id.return_value = {
                "session_id": 50,
                "match_id": 1,
                "hours": 2.0,
                "content_summary": "原內容",
                "homework": None,
                "student_performance": None,
                "next_plan": None,
                "visible_to_parent": False,
            }
            repo.get_match_for_create.return_value = {
                "match_id": 1, "status": "active", "tutor_user_id": 2,
            }

            resp = client.put(
                self.ENDPOINT.format(session_id=50),
                json={"content_summary": "原內容", "hours": 2.0},
                headers=tutor_headers,
            )

        assert resp.status_code == 200
        assert "無實際變動" in resp.json()["message"]
        repo.insert_edit_log.assert_not_called()

    def test_update_not_tutor_denied(self, client, parent_headers, mock_conn):
        """家長不能修改上課日誌。"""
        resp = client.put(
            self.ENDPOINT.format(session_id=50),
            json={"content_summary": "hacked"},
            headers=parent_headers,
        )
        assert resp.status_code == 403


# ━━━━━━━━━━ 列出課堂紀錄 ━━━━━━━━━━

class TestListSessions:
    ENDPOINT = "/api/sessions"

    def test_list_as_tutor(self, client, tutor_headers, mock_conn):
        """老師可列出所有日誌。"""
        with patch("app.routers.sessions.SessionRepository") as MockRepo:
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
        # 確認 parent_only=False（老師看全部）
        repo.list_by_match.assert_called_once_with(1, parent_only=False)

    def test_list_as_parent_filtered(self, client, parent_headers, mock_conn):
        """家長只看到 visible_to_parent=true 的日誌。"""
        with patch("app.routers.sessions.SessionRepository") as MockRepo:
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
        repo.list_by_match.assert_called_once_with(1, parent_only=True)


# ━━━━━━━━━━ 修改紀錄查詢 ━━━━━━━━━━

class TestEditLogs:
    ENDPOINT = "/api/sessions/{session_id}/edit-logs"

    def test_get_edit_logs_success(self, client, tutor_headers, mock_conn):
        """老師可查看修改紀錄。"""
        with patch("app.routers.sessions.SessionRepository") as MockRepo:
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
