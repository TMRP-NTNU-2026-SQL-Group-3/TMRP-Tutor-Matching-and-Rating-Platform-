"""Review API 測試：三向評價 / 7 天鎖定機制 / 重複評價被拒。"""

from unittest.mock import patch


def _match_participants(**overrides):
    base = {
        "match_id": 1,
        "status": "active",
        "tutor_user_id": 2,
        "parent_user_id": 1,
    }
    base.update(overrides)
    return base


# ━━━━━━━━━━ 建立評價 ━━━━━━━━━━

class TestCreateReview:
    ENDPOINT = "/api/reviews"

    def test_parent_to_tutor_success(self, client, parent_headers, mock_conn):
        """家長對老師評價成功。"""
        with patch("app.routers.reviews.ReviewRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = _match_participants()
            repo.find_existing.return_value = None
            repo.create.return_value = 10

            resp = client.post(self.ENDPOINT, json={
                "match_id": 1,
                "review_type": "parent_to_tutor",
                "rating_1": 5, "rating_2": 4,
                "comment": "很棒的老師",
            }, headers=parent_headers)

        assert resp.status_code == 200
        assert resp.json()["data"]["review_id"] == 10

    def test_tutor_to_parent_success(self, client, tutor_headers, mock_conn):
        """老師對家長評價成功。"""
        with patch("app.routers.reviews.ReviewRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = _match_participants()
            repo.find_existing.return_value = None
            repo.create.return_value = 11

            resp = client.post(self.ENDPOINT, json={
                "match_id": 1,
                "review_type": "tutor_to_parent",
                "rating_1": 4, "rating_2": 3,
            }, headers=tutor_headers)

        assert resp.status_code == 200
        assert resp.json()["data"]["review_id"] == 11

    def test_tutor_to_student_success(self, client, tutor_headers, mock_conn):
        """老師對學生評價成功。"""
        with patch("app.routers.reviews.ReviewRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = _match_participants()
            repo.find_existing.return_value = None
            repo.create.return_value = 12

            resp = client.post(self.ENDPOINT, json={
                "match_id": 1,
                "review_type": "tutor_to_student",
                "rating_1": 5, "rating_2": 5,
            }, headers=tutor_headers)

        assert resp.status_code == 200

    def test_duplicate_review_rejected(self, client, parent_headers, mock_conn):
        """重複評價回傳 409。"""
        with patch("app.routers.reviews.ReviewRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = _match_participants()
            repo.find_existing.return_value = {"review_id": 10}

            resp = client.post(self.ENDPOINT, json={
                "match_id": 1,
                "review_type": "parent_to_tutor",
                "rating_1": 5, "rating_2": 4,
            }, headers=parent_headers)

        assert resp.status_code == 409
        assert "已" in resp.json()["message"]

    def test_parent_cannot_review_as_tutor(self, client, parent_headers, mock_conn):
        """家長不能用 tutor_to_parent 類型評價。"""
        with patch("app.routers.reviews.ReviewRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = _match_participants()

            resp = client.post(self.ENDPOINT, json={
                "match_id": 1,
                "review_type": "tutor_to_parent",
                "rating_1": 3, "rating_2": 3,
            }, headers=parent_headers)

        assert resp.status_code == 403

    def test_invalid_review_type(self, client, parent_headers, mock_conn):
        """不合法的評價類型回傳 400。"""
        with patch("app.routers.reviews.ReviewRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = _match_participants()

            resp = client.post(self.ENDPOINT, json={
                "match_id": 1,
                "review_type": "student_to_tutor",
                "rating_1": 3, "rating_2": 3,
            }, headers=parent_headers)

        assert resp.status_code == 400

    def test_match_not_found(self, client, parent_headers, mock_conn):
        """找不到配對回傳 404。"""
        with patch("app.routers.reviews.ReviewRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_for_create.return_value = None

            resp = client.post(self.ENDPOINT, json={
                "match_id": 999,
                "review_type": "parent_to_tutor",
                "rating_1": 5, "rating_2": 5,
            }, headers=parent_headers)

        assert resp.status_code == 404


# ━━━━━━━━━━ 7 天鎖定 ━━━━━━━━━━

class TestReviewLock:
    ENDPOINT = "/api/reviews/{review_id}"

    def test_update_within_lock_period(self, client, parent_headers, mock_conn):
        """7 天內可修改評價。"""
        with patch("app.routers.reviews.ReviewRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_for_update.return_value = {
                "review_id": 10,
                "reviewer_user_id": 1,
                "is_locked": False,
            }

            resp = client.patch(
                self.ENDPOINT.format(review_id=10),
                json={"rating_1": 4, "comment": "更新評價"},
                headers=parent_headers,
            )

        assert resp.status_code == 200

    def test_update_after_lock(self, client, parent_headers, mock_conn):
        """超過 7 天鎖定後無法修改。"""
        with patch("app.routers.reviews.ReviewRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_for_update.return_value = {
                "review_id": 10,
                "reviewer_user_id": 1,
                "is_locked": True,
            }

            resp = client.patch(
                self.ENDPOINT.format(review_id=10),
                json={"rating_1": 1},
                headers=parent_headers,
            )

        assert resp.status_code == 400
        assert "7 天" in resp.json()["message"]

    def test_update_not_reviewer(self, client, tutor_headers, mock_conn):
        """非評價者無法修改。"""
        with patch("app.routers.reviews.ReviewRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_for_update.return_value = {
                "review_id": 10,
                "reviewer_user_id": 1,  # parent is reviewer
                "is_locked": False,
            }

            resp = client.patch(
                self.ENDPOINT.format(review_id=10),
                json={"rating_1": 1},
                headers=tutor_headers,  # tutor (user_id=2) tries
            )

        assert resp.status_code == 403


# ━━━━━━━━━━ 列出評價 ━━━━━━━━━━

class TestListReviews:
    ENDPOINT = "/api/reviews"

    def test_list_as_participant(self, client, parent_headers, mock_conn):
        """配對參與者可列出評價。"""
        with patch("app.routers.reviews.ReviewRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_participants.return_value = _match_participants()
            repo.list_by_match.return_value = [
                {"review_id": 10, "review_type": "parent_to_tutor"},
            ]

            resp = client.get(
                self.ENDPOINT, params={"match_id": 1},
                headers=parent_headers,
            )

        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    def test_list_non_participant_denied(self, client, admin_headers, mock_conn):
        """非參與者且非管理員無法列出（此測試用 admin 驗證可以）。"""
        with patch("app.routers.reviews.ReviewRepository") as MockRepo:
            repo = MockRepo.return_value
            repo.get_match_participants.return_value = _match_participants()
            repo.list_by_match.return_value = []

            resp = client.get(
                self.ENDPOINT, params={"match_id": 1},
                headers=admin_headers,
            )

        # admin 可以查看
        assert resp.status_code == 200
