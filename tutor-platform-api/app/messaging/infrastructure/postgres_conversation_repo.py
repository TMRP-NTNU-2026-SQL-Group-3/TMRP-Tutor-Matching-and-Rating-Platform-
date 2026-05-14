"""DB-L05: Dedicated repository for conversation operations.

Previously all conversation queries lived in PostgresMessageRepository.
Splitting them out follows the single-responsibility principle and makes
it easier to test conversation logic in isolation.
"""

from psycopg2.errors import UniqueViolation

from app.messaging.domain.ports import IConversationRepository
from app.shared.infrastructure.base_repository import BaseRepository
from app.shared.infrastructure.database_tx import transaction


class PostgresConversationRepository(BaseRepository, IConversationRepository):

    def find_conversations_for_user(self, user_id: int) -> list[dict]:
        # Pulls the latest message via a LATERAL subquery so the list view can
        # show a message preview without an N+1 round trip per conversation.
        #
        # NOTE on empty conversations: LEFT JOIN LATERAL returns one row per
        # conversation regardless of whether `messages` has a match. For a
        # conversation with no messages, `last_message_content` and
        # `last_message_sender_id` are NULL — callers must render a
        # placeholder rather than treating NULL as an error.
        #
        # The CTE binds user_id once so the value doesn't have to be repeated
        # as four separate positional parameters across the CASE expressions
        # and the WHERE clause.
        return self.fetch_all(
            """WITH me(uid) AS (VALUES (%s))
               SELECT c.conversation_id, c.user_a_id, c.user_b_id,
                      c.created_at, c.last_message_at,
                      CASE WHEN c.user_a_id = me.uid THEN u_b.display_name ELSE u_a.display_name END AS other_name,
                      CASE WHEN c.user_a_id = me.uid THEN c.user_b_id ELSE c.user_a_id END AS other_user_id,
                      lm.content AS last_message_content,
                      lm.sender_user_id AS last_message_sender_id
               FROM me, conversations c
               INNER JOIN users u_a ON c.user_a_id = u_a.user_id
               INNER JOIN users u_b ON c.user_b_id = u_b.user_id
               LEFT JOIN LATERAL (
                   SELECT m.content, m.sender_user_id
                   FROM messages m
                   WHERE m.conversation_id = c.conversation_id
                   ORDER BY m.sent_at DESC, m.message_id DESC
                   LIMIT 1
               ) lm ON TRUE
               WHERE c.user_a_id = me.uid OR c.user_b_id = me.uid
               ORDER BY c.last_message_at DESC NULLS LAST""",
            (user_id,),
        )

    def _find_conversation_between(self, user_a_id: int, user_b_id: int) -> dict | None:
        a, b = min(user_a_id, user_b_id), max(user_a_id, user_b_id)
        return self.fetch_one(
            "SELECT * FROM conversations WHERE user_a_id = %s AND user_b_id = %s",
            (a, b),
        )

    def _create_conversation(self, user_a_id: int, user_b_id: int) -> int:
        a, b = min(user_a_id, user_b_id), max(user_a_id, user_b_id)
        return self.execute_returning_id(
            """INSERT INTO conversations (user_a_id, user_b_id)
               VALUES (%s, %s) RETURNING conversation_id""",
            (a, b),
        )

    def get_or_create_conversation(self, user_a_id: int, user_b_id: int) -> int:
        if user_a_id == user_b_id:
            raise ValueError("Cannot create a conversation with yourself")
        try:
            with transaction(self.conn):
                existing = self._find_conversation_between(user_a_id, user_b_id)
                if existing:
                    return existing["conversation_id"]
                return self._create_conversation(user_a_id, user_b_id)
        except UniqueViolation:
            existing = self._find_conversation_between(user_a_id, user_b_id)
            if existing:
                return existing["conversation_id"]
            raise

    def user_is_participant(self, conversation_id: int, user_id: int) -> bool:
        row = self.fetch_one(
            "SELECT COUNT(*) AS cnt FROM conversations WHERE conversation_id = %s AND (user_a_id = %s OR user_b_id = %s)",
            (conversation_id, user_id, user_id),
        )
        return row["cnt"] > 0 if row else False

    def has_valid_match_between(self, user_a_id: int, user_b_id: int) -> bool:
        # ARCH-17: match-existence guard moved here from the service layer so
        # the application service no longer constructs BaseRepository directly.
        #
        # Only `rejected` matches are excluded. `ended` and `cancelled` matches
        # intentionally still allow messaging so the two parties can coordinate
        # after a match closes (e.g., final invoices, references).
        row = self.fetch_one(
            """SELECT 1
                 FROM matches m
                 JOIN tutors   t  ON m.tutor_id   = t.tutor_id
                 JOIN students st ON m.student_id = st.student_id
                 JOIN users ut    ON ut.user_id = t.user_id
                 JOIN users up    ON up.user_id = st.parent_user_id
                WHERE m.status <> 'rejected'
                  AND ut.role = 'tutor'
                  AND up.role = 'parent'
                  AND ( (t.user_id = %s AND st.parent_user_id = %s)
                     OR (t.user_id = %s AND st.parent_user_id = %s) )
                LIMIT 1""",
            (user_a_id, user_b_id, user_b_id, user_a_id),
        )
        return row is not None
