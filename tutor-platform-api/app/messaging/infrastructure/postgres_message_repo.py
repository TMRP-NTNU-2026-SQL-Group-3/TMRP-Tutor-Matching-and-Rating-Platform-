from psycopg2 import sql

from app.messaging.domain.ports import IMessageRepository
from app.shared.infrastructure.base_repository import BaseRepository
from app.shared.infrastructure.database_tx import transaction


class PostgresMessageRepository(BaseRepository, IMessageRepository):

    def get_messages(self, conversation_id: int, *, limit: int, before_id: int | None = None) -> list[dict]:
        # Fetch the most recent `limit` messages (optionally older than `before_id`)
        # in DESC order, then reverse so the UI still renders oldest-first.
        conditions = [sql.SQL("msg.conversation_id = %s")]
        params: list = [conversation_id]
        if before_id is not None:
            conditions.append(sql.SQL("msg.message_id < %s"))
            params.append(before_id)
        params.append(limit)
        # B4: Chronological order must key on sent_at — auto-increment
        # message_id is not a reliable proxy (gaps from rollbacks and
        # out-of-order commits can invert creation order). message_id
        # DESC stays as a deterministic tiebreaker when two rows share
        # the exact same sent_at, and still matches the cursor semantics
        # of `before_id` above.
        query = sql.SQL(
            """SELECT msg.message_id, msg.sender_user_id, msg.content, msg.sent_at,
                       u.display_name AS sender_name
                FROM messages msg INNER JOIN users u ON msg.sender_user_id = u.user_id
                WHERE {where}
                ORDER BY msg.sent_at DESC, msg.message_id DESC
                LIMIT %s"""
        ).format(where=sql.SQL(" AND ").join(conditions))
        rows = self.fetch_all(query, tuple(params))
        return list(reversed(rows))

    def message_in_conversation(self, message_id: int, conversation_id: int) -> bool:
        row = self.fetch_one(
            "SELECT 1 FROM messages WHERE message_id = %s AND conversation_id = %s",
            (message_id, conversation_id),
        )
        return row is not None

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
