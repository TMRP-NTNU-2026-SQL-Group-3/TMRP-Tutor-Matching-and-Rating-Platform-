from app.messaging.domain.ports import IMessageRepository
from app.shared.infrastructure.base_repository import BaseRepository
from app.shared.infrastructure.database_tx import transaction


class PostgresMessageRepository(BaseRepository, IMessageRepository):

    def find_conversations_for_user(self, user_id: int) -> list[dict]:
        return self.fetch_all(
            """SELECT c.conversation_id, c.user_a_id, c.user_b_id,
                      c.created_at, c.last_message_at,
                      CASE WHEN c.user_a_id = %s THEN u_b.display_name ELSE u_a.display_name END AS other_name,
                      CASE WHEN c.user_a_id = %s THEN c.user_b_id ELSE c.user_a_id END AS other_user_id
               FROM conversations c
               INNER JOIN users u_a ON c.user_a_id = u_a.user_id
               INNER JOIN users u_b ON c.user_b_id = u_b.user_id
               WHERE c.user_a_id = %s OR c.user_b_id = %s
               ORDER BY c.last_message_at DESC""",
            (user_id, user_id, user_id, user_id),
        )

    def _find_conversation_between(self, user_a_id: int, user_b_id: int) -> dict | None:
        return self.fetch_one(
            """SELECT * FROM conversations
               WHERE (user_a_id = %s AND user_b_id = %s)
               OR (user_a_id = %s AND user_b_id = %s)""",
            (user_a_id, user_b_id, user_b_id, user_a_id),
        )

    def _create_conversation(self, user_a_id: int, user_b_id: int) -> int:
        a, b = min(user_a_id, user_b_id), max(user_a_id, user_b_id)
        return self.execute_returning_id(
            """INSERT INTO conversations (user_a_id, user_b_id, created_at, last_message_at)
               VALUES (%s, %s, NOW(), NOW()) RETURNING conversation_id""",
            (a, b),
        )

    def get_or_create_conversation(self, user_a_id: int, user_b_id: int) -> int:
        try:
            with transaction(self.conn):
                existing = self._find_conversation_between(user_a_id, user_b_id)
                if existing:
                    return existing["conversation_id"]
                return self._create_conversation(user_a_id, user_b_id)
        except Exception:
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

    def get_messages(self, conversation_id: int, *, limit: int, before_id: int | None = None) -> list[dict]:
        # Fetch the most recent `limit` messages (optionally older than `before_id`)
        # in DESC order, then reverse so the UI still renders oldest-first.
        params: list = [conversation_id]
        where = "msg.conversation_id = %s"
        if before_id is not None:
            where += " AND msg.message_id < %s"
            params.append(before_id)
        params.append(limit)
        rows = self.fetch_all(
            f"""SELECT msg.message_id, msg.sender_user_id, msg.content, msg.sent_at,
                       u.display_name AS sender_name
                FROM messages msg INNER JOIN users u ON msg.sender_user_id = u.user_id
                WHERE {where}
                ORDER BY msg.message_id DESC
                LIMIT %s""",
            tuple(params),
        )
        return list(reversed(rows))

    def send_message(self, conversation_id: int, sender_user_id: int, content: str) -> int:
        with transaction(self.conn):
            self.cursor.execute(
                "INSERT INTO messages (conversation_id, sender_user_id, content, sent_at) VALUES (%s, %s, %s, NOW()) RETURNING message_id",
                (conversation_id, sender_user_id, content),
            )
            msg_id = self.cursor.fetchone()[0]
            self.cursor.execute(
                "UPDATE conversations SET last_message_at = NOW() WHERE conversation_id = %s",
                (conversation_id,),
            )
        return msg_id
