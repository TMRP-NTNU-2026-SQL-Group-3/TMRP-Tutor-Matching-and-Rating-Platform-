from app.messaging.domain.ports import IMessageRepository
from app.shared.infrastructure.base_repository import BaseRepository
from app.shared.infrastructure.database_tx import transaction


class PostgresMessageRepository(BaseRepository, IMessageRepository):

    def get_messages(self, conversation_id: int, *, limit: int, before_id: int | None = None) -> list[dict]:
        # Fetch the most recent `limit` messages (optionally older than `before_id`)
        # in DESC order, then reverse so the UI still renders oldest-first.
        clauses = ["msg.conversation_id = %s"]
        params: list = [conversation_id]
        if before_id is not None:
            clauses.append("msg.message_id < %s")
            params.append(before_id)
        params.append(limit)
        where_sql = " AND ".join(clauses)
        rows = self.fetch_all(
            # B4: Chronological order must key on sent_at — auto-increment
            # message_id is not a reliable proxy (gaps from rollbacks and
            # out-of-order commits can invert creation order). message_id
            # DESC stays as a deterministic tiebreaker when two rows share
            # the exact same sent_at, and still matches the cursor semantics
            # of `before_id` above.
            f"""SELECT msg.message_id, msg.sender_user_id, msg.content, msg.sent_at,
                       u.display_name AS sender_name
                FROM messages msg INNER JOIN users u ON msg.sender_user_id = u.user_id
                WHERE {where_sql}
                ORDER BY msg.sent_at DESC, msg.message_id DESC
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
