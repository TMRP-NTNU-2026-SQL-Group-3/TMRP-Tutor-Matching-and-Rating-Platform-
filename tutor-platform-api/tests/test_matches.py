"""Match 狀態機測試：建立配對、8 種合法轉換、非法轉換被拒、權限檢查。"""

from unittest.mock import patch


def _match_row(**overrides):
    """產生一筆完整的 match dict，方便各測試覆寫欄位。"""
    base = {
        "match_id": 1,
        "tutor_id": 1,
        "student_id": 1,
        "subject_id": 1,
        "hourly_rate": 600,
        "sessions_per_week": 2,
        "status": "pending",
        "want_trial": False,
        "invite_message": None,
        "subject_name": "數學",
        "student_name": "小明",
        "tutor_display_name": "陳老師",
        "parent_user_id": 1,    # parent = user 1
        "tutor_user_id": 2,     # tutor  = user 2
        "terminated_by": None,
        "termination_reason": None,
    }
    base.update(overrides)
    return base


# ━━━━━━━━━━ 建立配對 ━━━━━━━━━━

class TestCreateMatch:
    ENDPOINT = "/api/matches"

    def test_create_success(self, client, parent_headers, mock_conn):
        """家長建立配對邀請成功。"""
        with (
            patch("app.routers.matches.StudentRepository") as MockStu,
            patch("app.routers.matches.TutorRepository") as MockTut,
            patch("app.routers.matches.MatchRepository") as MockMatch,
        ):
            MockStu.return_value.find_by_id.return_value = {
                "student_id": 1, "parent_user_id": 1,
            }
            MockTut.return_value.find_by_id.return_value = {"tutor_id": 1}
            MockTut.return_value.get_subjects.return_value = [
                {"subject_id": 2, "hourly_rate": 600},
            ]
            MockMatch.return_value.check_duplicate_active.return_value = False
            MockTut.return_value.get_active_student_count.return_value = 0
            MockMatch.return_value.create.return_value = 100

            resp = client.post(self.ENDPOINT, json={
                "tutor_id": 1, "student_id": 1, "subject_id": 2,
                "hourly_rate": 600, "sessions_per_week": 2,
            }, headers=parent_headers)

        assert resp.status_code == 200
        assert resp.json()["data"]["match_id"] == 100

    def test_create_not_parent_role(self, client, tutor_headers):
        """家教角色無法建立配對（403）。"""
        resp = client.post(self.ENDPOINT, json={
            "tutor_id": 1, "student_id": 1, "subject_id": 2,
            "hourly_rate": 600, "sessions_per_week": 2,
        }, headers=tutor_headers)
        assert resp.status_code == 403

    def test_create_duplicate_active(self, client, parent_headers, mock_conn):
        """重複配對回傳 409。"""
        with (
            patch("app.routers.matches.StudentRepository") as MockStu,
            patch("app.routers.matches.TutorRepository") as MockTut,
            patch("app.routers.matches.MatchRepository") as MockMatch,
        ):
            MockStu.return_value.find_by_id.return_value = {
                "student_id": 1, "parent_user_id": 1,
            }
            MockTut.return_value.find_by_id.return_value = {"tutor_id": 1}
            MockTut.return_value.get_subjects.return_value = [
                {"subject_id": 2, "hourly_rate": 600},
            ]
            MockMatch.return_value.check_duplicate_active.return_value = True

            resp = client.post(self.ENDPOINT, json={
                "tutor_id": 1, "student_id": 1, "subject_id": 2,
                "hourly_rate": 600, "sessions_per_week": 2,
            }, headers=parent_headers)

        assert resp.status_code == 409


# ━━━━━━━━━━ 狀態機轉換 ━━━━━━━━━━

class TestMatchStatusTransitions:
    ENDPOINT = "/api/matches/{match_id}/status"

    def _patch_and_call(self, client, headers, match_id, match_data, action, reason=None):
        """輔助方法：patch MatchRepository 並發送 PATCH 請求。"""
        with patch("app.routers.matches.MatchRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.find_by_id.return_value = match_data
            body = {"action": action}
            if reason:
                body["reason"] = reason
            return client.patch(
                self.ENDPOINT.format(match_id=match_id),
                json=body,
                headers=headers,
            )

    # ── 合法轉換 ──

    def test_pending_cancel_by_parent(self, client, parent_headers):
        """pending → cancelled：家長取消。"""
        match = _match_row(status="pending")
        resp = self._patch_and_call(client, parent_headers, 1, match, "cancel")
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "cancelled"

    def test_pending_reject_by_tutor(self, client, tutor_headers):
        """pending → rejected：家教拒絕。"""
        match = _match_row(status="pending")
        resp = self._patch_and_call(client, tutor_headers, 1, match, "reject")
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "rejected"

    def test_pending_accept_to_trial(self, client, tutor_headers):
        """pending → trial：家教接受（有試教）。"""
        match = _match_row(status="pending", want_trial=True)
        resp = self._patch_and_call(client, tutor_headers, 1, match, "accept")
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "trial"

    def test_pending_accept_to_active(self, client, tutor_headers):
        """pending → active：家教接受（無試教）。"""
        match = _match_row(status="pending", want_trial=False)
        resp = self._patch_and_call(client, tutor_headers, 1, match, "accept")
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "active"

    def test_trial_confirm(self, client, tutor_headers):
        """trial → active：確認試教。"""
        match = _match_row(status="trial")
        resp = self._patch_and_call(client, tutor_headers, 1, match, "confirm_trial")
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "active"

    def test_trial_reject(self, client, parent_headers):
        """trial → rejected：拒絕試教。"""
        match = _match_row(status="trial")
        resp = self._patch_and_call(client, parent_headers, 1, match, "reject_trial")
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "rejected"

    def test_active_pause(self, client, tutor_headers):
        """active → paused：暫停。"""
        match = _match_row(status="active")
        resp = self._patch_and_call(client, tutor_headers, 1, match, "pause")
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "paused"

    def test_paused_resume(self, client, parent_headers):
        """paused → active：恢復。"""
        match = _match_row(status="paused")
        resp = self._patch_and_call(client, parent_headers, 1, match, "resume")
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "active"

    def test_active_terminate(self, client, tutor_headers):
        """active → terminating：發起終止。"""
        match = _match_row(status="active")
        resp = self._patch_and_call(
            client, tutor_headers, 1, match, "terminate", reason="搬家了",
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "terminating"

    def test_terminating_agree(self, client, parent_headers):
        """terminating → ended：對方同意終止。"""
        match = _match_row(status="terminating", terminated_by=2)
        resp = self._patch_and_call(client, parent_headers, 1, match, "agree_terminate")
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "ended"

    def test_terminating_disagree(self, client, parent_headers):
        """terminating → 回復前狀態：對方不同意終止。"""
        match = _match_row(
            status="terminating",
            terminated_by=2,
            termination_reason="active|搬家了",
        )
        resp = self._patch_and_call(client, parent_headers, 1, match, "disagree_terminate")
        assert resp.status_code == 200
        assert resp.json()["data"]["new_status"] == "active"

    # ── 非法轉換 ──

    def test_illegal_transition_rejected(self, client, tutor_headers):
        """已結束的配對不能再操作。"""
        match = _match_row(status="ended")
        resp = self._patch_and_call(client, tutor_headers, 1, match, "accept")
        assert resp.status_code == 400
        assert "無法" in resp.json()["message"]

    def test_pending_cannot_pause(self, client, tutor_headers):
        """pending 狀態不能暫停。"""
        match = _match_row(status="pending")
        resp = self._patch_and_call(client, tutor_headers, 1, match, "pause")
        assert resp.status_code == 400

    # ── 權限檢查 ──

    def test_parent_cannot_accept(self, client, parent_headers):
        """家長不能執行 accept（只有家教可以）。"""
        match = _match_row(status="pending")
        resp = self._patch_and_call(client, parent_headers, 1, match, "accept")
        assert resp.status_code == 403

    def test_tutor_cannot_cancel(self, client, tutor_headers):
        """家教不能取消（只有家長可以）。"""
        match = _match_row(status="pending")
        resp = self._patch_and_call(client, tutor_headers, 1, match, "cancel")
        assert resp.status_code == 403

    def test_terminate_requires_reason(self, client, tutor_headers):
        """終止需要提供原因。"""
        match = _match_row(status="active")
        resp = self._patch_and_call(client, tutor_headers, 1, match, "terminate")
        assert resp.status_code == 400
        assert "原因" in resp.json()["message"]

    def test_terminator_cannot_agree_own(self, client, tutor_headers):
        """發起終止方不能自己同意。"""
        match = _match_row(status="terminating", terminated_by=2)
        resp = self._patch_and_call(client, tutor_headers, 1, match, "agree_terminate")
        assert resp.status_code == 403
