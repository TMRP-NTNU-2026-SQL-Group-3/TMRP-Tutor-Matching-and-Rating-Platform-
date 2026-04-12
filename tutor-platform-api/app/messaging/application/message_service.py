"""Application service for conversations and messages.

Owns resource-ownership (participant) checks and target-user lookups so the
router layer only parses HTTP inputs and shapes responses.
"""

from app.messaging.domain.exceptions import (
    EmptyMessageError,
    NotConversationParticipantError,
    SelfConversationError,
    TargetUserNotFoundError,
)
from app.messaging.domain.ports import IMessageRepository
from app.shared.infrastructure.base_repository import BaseRepository


class MessageAppService:
    def __init__(self, repo: IMessageRepository, conn):
        self._repo = repo
        # User existence is a catalog-adjacent concern, but we have no dedicated
        # user-query port yet; reuse BaseRepository directly for this lookup.
        self._user_lookup = BaseRepository(conn)

    def create_conversation(self, *, user_id: int, target_user_id: int) -> int:
        if user_id == target_user_id:
            raise SelfConversationError()
        target = self._user_lookup.fetch_one(
            "SELECT user_id FROM users WHERE user_id = %s", (target_user_id,)
        )
        if not target:
            raise TargetUserNotFoundError()
        return self._repo.get_or_create_conversation(user_id, target_user_id)

    def list_conversations(self, *, user_id: int) -> list[dict]:
        return self._repo.find_conversations_for_user(user_id)

    def get_messages(
        self,
        *,
        conversation_id: int,
        user_id: int,
        limit: int = 100,
        before_id: int | None = None,
    ) -> list[dict]:
        if not self._repo.user_is_participant(conversation_id, user_id):
            raise NotConversationParticipantError("查看")
        return self._repo.get_messages(conversation_id, limit=limit, before_id=before_id)

    def send_message(self, *, conversation_id: int, user_id: int, content: str) -> int:
        # MessageSend.content is already trimmed + non-empty via TrimmedStr,
        # but keep a strip-and-check here for direct service callers that
        # may not go through the Pydantic schema.
        cleaned = (content or "").strip()
        if not cleaned:
            raise EmptyMessageError()
        if not self._repo.user_is_participant(conversation_id, user_id):
            raise NotConversationParticipantError("在此對話中發送訊息")
        return self._repo.send_message(conversation_id, user_id, cleaned)
