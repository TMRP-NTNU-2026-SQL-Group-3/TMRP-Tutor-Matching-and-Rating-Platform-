"""Application service for conversations and messages.

Owns resource-ownership (participant) checks and target-user lookups so the
router layer only parses HTTP inputs and shapes responses.
"""

from app.messaging.domain.exceptions import (
    ConversationNotAllowedError,
    EmptyMessageError,
    NotConversationParticipantError,
    SelfConversationError,
)
from app.messaging.domain.ports import IConversationRepository, IMessageRepository
from app.shared.infrastructure.base_repository import BaseRepository


class MessageAppService:
    def __init__(self, repo: IMessageRepository, conv_repo: IConversationRepository, conn):
        self._repo = repo
        self._conv_repo = conv_repo
        # User existence is a catalog-adjacent concern, but we have no dedicated
        # user-query port yet; reuse BaseRepository directly for this lookup.
        self._user_lookup = BaseRepository(conn)

    def create_conversation(self, *, user_id: int, target_user_id: int) -> int:
        if user_id == target_user_id:
            raise SelfConversationError()
        # MEDIUM-6: require at least one non-rejected match between the two
        # users before allowing a conversation to be opened. This prevents
        # (a) enumerating valid user IDs via the 404/200 oracle and
        # (b) unsolicited DMs to arbitrary registered users.
        # "Rejected" matches don't count — a rejection is an explicit
        # refusal of contact.
        #
        # Role pairing is enforced explicitly in the same query: exactly
        # one side must have role='tutor' and the other role='parent'.
        # Relying on the tutors/students join alone would silently permit
        # a conversation if role columns and tutor/student rows ever
        # diverged (e.g. after an out-of-band role change). The single
        # generic 403 keeps the error shape indistinguishable from
        # "user does not exist".
        row = self._user_lookup.fetch_one(
            """SELECT 1
                 FROM matches m
                 JOIN tutors  t   ON m.tutor_id   = t.tutor_id
                 JOIN students st ON m.student_id = st.student_id
                 JOIN users ut    ON ut.user_id = t.user_id
                 JOIN users up    ON up.user_id = st.parent_user_id
                WHERE m.status <> 'rejected'
                  AND ut.role = 'tutor'
                  AND up.role = 'parent'
                  AND ( (t.user_id = %s AND st.parent_user_id = %s)
                     OR (t.user_id = %s AND st.parent_user_id = %s) )
                LIMIT 1""",
            (user_id, target_user_id, target_user_id, user_id),
        )
        if not row:
            raise ConversationNotAllowedError()
        return self._conv_repo.get_or_create_conversation(user_id, target_user_id)

    def list_conversations(self, *, user_id: int) -> list[dict]:
        return self._conv_repo.find_conversations_for_user(user_id)

    def get_messages(
        self,
        *,
        conversation_id: int,
        user_id: int,
        limit: int = 100,
        before_id: int | None = None,
    ) -> list[dict]:
        if not self._conv_repo.user_is_participant(conversation_id, user_id):
            raise NotConversationParticipantError("查看")
        return self._repo.get_messages(conversation_id, limit=limit, before_id=before_id)

    def send_message(self, *, conversation_id: int, user_id: int, content: str) -> int:
        # MessageSend.content is already trimmed + non-empty via TrimmedStr,
        # but keep a strip-and-check here for direct service callers that
        # may not go through the Pydantic schema.
        cleaned = (content or "").strip()
        if not cleaned:
            raise EmptyMessageError()
        if not self._conv_repo.user_is_participant(conversation_id, user_id):
            raise NotConversationParticipantError("在此對話中發送訊息")
        return self._repo.send_message(conversation_id, user_id, cleaned)
