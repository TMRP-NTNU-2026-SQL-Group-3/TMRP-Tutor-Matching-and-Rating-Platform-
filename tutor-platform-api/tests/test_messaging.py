"""Messaging router tests: conversations and message sending.

MessageAppService is patched at its construction site in
app.messaging.api.dependencies so no real infrastructure is contacted.
Both parent and tutor roles are permitted; admin is excluded.
"""

from unittest.mock import patch

_MSG_SERVICE = "app.messaging.api.dependencies.MessageAppService"
_CSRF = "test-csrf-token"


class TestCreateConversation:
    ENDPOINT = "/api/messages/conversations"

    def test_parent_can_open_conversation(self, client, parent_headers, mock_conn):
        """Parent can start a conversation with a tutor."""
        with patch(_MSG_SERVICE) as MockService:
            MockService.return_value.create_conversation.return_value = 1

            resp = client.post(
                self.ENDPOINT,
                json={"target_user_id": 2},
                headers={**parent_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 201
        assert resp.json()["data"]["conversation_id"] == 1

    def test_tutor_can_open_conversation(self, client, tutor_headers, mock_conn):
        """Tutors may also initiate conversations."""
        with patch(_MSG_SERVICE) as MockService:
            MockService.return_value.create_conversation.return_value = 2

            resp = client.post(
                self.ENDPOINT,
                json={"target_user_id": 1},
                headers={**tutor_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 201

    def test_admin_cannot_create_conversation(self, client, admin_headers, mock_conn):
        """Admin role is excluded from messaging endpoints."""
        resp = client.post(
            self.ENDPOINT,
            json={"target_user_id": 1},
            headers={**admin_headers, "X-CSRF-Token": _CSRF},
            cookies={"csrf_token": _CSRF},
        )
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, client):
        """Missing token is rejected before any service call."""
        resp = client.post(
            self.ENDPOINT,
            json={"target_user_id": 1},
            headers={"X-CSRF-Token": _CSRF},
            cookies={"csrf_token": _CSRF},
        )
        assert resp.status_code == 401


class TestListConversations:
    ENDPOINT = "/api/messages/conversations"

    def test_parent_can_list_conversations(self, client, parent_headers, mock_conn):
        """Parent retrieves all their open conversations."""
        with patch(_MSG_SERVICE) as MockService:
            MockService.return_value.list_conversations.return_value = [
                {"conversation_id": 1, "other_user_id": 2, "last_message": "Hi"},
            ]

            resp = client.get(self.ENDPOINT, headers=parent_headers)

        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    def test_tutor_can_list_conversations(self, client, tutor_headers, mock_conn):
        with patch(_MSG_SERVICE) as MockService:
            MockService.return_value.list_conversations.return_value = []

            resp = client.get(self.ENDPOINT, headers=tutor_headers)

        assert resp.status_code == 200


class TestGetMessages:
    def test_participant_can_read_messages(self, client, parent_headers, mock_conn):
        """Authenticated participant fetches messages in their conversation."""
        with patch(_MSG_SERVICE) as MockService:
            MockService.return_value.get_messages.return_value = [
                {"message_id": 1, "content": "Hello"},
                {"message_id": 2, "content": "World"},
            ]

            resp = client.get(
                "/api/messages/conversations/1",
                headers=parent_headers,
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["items"]) == 2
        assert data["oldest_message_id"] == 1

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/api/messages/conversations/1")
        assert resp.status_code == 401


class TestSendMessage:
    def test_participant_can_send_message(self, client, parent_headers, mock_conn):
        """Authenticated participant sends a message and receives the new message_id."""
        with patch(_MSG_SERVICE) as MockService:
            MockService.return_value.send_message.return_value = 10

            resp = client.post(
                "/api/messages/conversations/1/messages",
                json={"content": "Hello!"},
                headers={**parent_headers, "X-CSRF-Token": _CSRF},
                cookies={"csrf_token": _CSRF},
            )

        assert resp.status_code == 201
        assert resp.json()["data"]["message_id"] == 10

    def test_empty_content_is_rejected(self, client, parent_headers, mock_conn):
        """TrimmedStr rejects whitespace-only content at the schema layer."""
        resp = client.post(
            "/api/messages/conversations/1/messages",
            json={"content": "   "},
            headers={**parent_headers, "X-CSRF-Token": _CSRF},
            cookies={"csrf_token": _CSRF},
        )
        assert resp.status_code == 422

    def test_unauthenticated_returns_401(self, client):
        resp = client.post(
            "/api/messages/conversations/1/messages",
            json={"content": "Hi"},
            headers={"X-CSRF-Token": _CSRF},
            cookies={"csrf_token": _CSRF},
        )
        assert resp.status_code == 401
