from app.database_tx import transaction
from app.repositories.base import BaseRepository


class MessageRepository(BaseRepository):

    def find_conversations_for_user(self, user_id: int) -> list[dict]:
        sql = """
            SELECT c.conversation_id, c.user_a_id, c.user_b_id,
                   c.created_at, c.last_message_at,
                   CASE WHEN c.user_a_id = %s THEN u_b.display_name ELSE u_a.display_name END AS other_name,
                   CASE WHEN c.user_a_id = %s THEN c.user_b_id ELSE c.user_a_id END AS other_user_id
            FROM conversations c
            INNER JOIN users u_a ON c.user_a_id = u_a.user_id
            INNER JOIN users u_b ON c.user_b_id = u_b.user_id
            WHERE c.user_a_id = %s OR c.user_b_id = %s
            ORDER BY c.last_message_at DESC
        """
        return self.fetch_all(sql, (user_id, user_id, user_id, user_id))

    def find_conversation_by_id(self, conversation_id: int) -> dict | None:
        sql = "SELECT * FROM conversations WHERE conversation_id = %s"
        return self.fetch_one(sql, (conversation_id,))

    def find_conversation_between(self, user_a_id: int, user_b_id: int) -> dict | None:
        sql = """
            SELECT * FROM conversations
            WHERE (user_a_id = %s AND user_b_id = %s)
            OR (user_a_id = %s AND user_b_id = %s)
        """
        return self.fetch_one(sql, (user_a_id, user_b_id, user_b_id, user_a_id))

    def create_conversation(self, user_a_id: int, user_b_id: int) -> int:
        a, b = min(user_a_id, user_b_id), max(user_a_id, user_b_id)
        sql = """
            INSERT INTO conversations (user_a_id, user_b_id, created_at, last_message_at)
            VALUES (%s, %s, NOW(), NOW())
            RETURNING conversation_id
        """
        return self.execute_returning_id(sql, (a, b))

    def get_or_create_conversation(self, user_a_id: int, user_b_id: int) -> int:
        # T-BIZ-02: 在交易中檢查並建立，防止並發重複建立。
        # 若因 UNIQUE 約束衝突，交易 rollback 後 fallback 查詢已存在的對話。
        try:
            with transaction(self.conn):
                existing = self.find_conversation_between(user_a_id, user_b_id)
                if existing:
                    return existing["conversation_id"]
                return self.create_conversation(user_a_id, user_b_id)
        except Exception:
            # 並發插入導致 UNIQUE 約束衝突，transaction 已 rollback，
            # 連線已恢復可用狀態，安全地查詢已由另一方建立的對話
            existing = self.find_conversation_between(user_a_id, user_b_id)
            if existing:
                return existing["conversation_id"]
            raise

    def get_messages(self, conversation_id: int) -> list[dict]:
        sql = """
            SELECT msg.message_id, msg.sender_user_id, msg.content, msg.sent_at,
                   u.display_name AS sender_name
            FROM messages msg
            INNER JOIN users u ON msg.sender_user_id = u.user_id
            WHERE msg.conversation_id = %s
            ORDER BY msg.sent_at ASC
        """
        return self.fetch_all(sql, (conversation_id,))

    def send_message(self, conversation_id: int, sender_user_id: int, content: str) -> int:
        sql = """
            INSERT INTO messages (conversation_id, sender_user_id, content, sent_at)
            VALUES (%s, %s, %s, NOW())
            RETURNING message_id
        """
        with transaction(self.conn):
            self.cursor.execute(sql, (conversation_id, sender_user_id, content))
            msg_id = self.cursor.fetchone()[0]
            self.cursor.execute(
                "UPDATE conversations SET last_message_at = NOW() WHERE conversation_id = %s",
                (conversation_id,),
            )
        return msg_id

    def user_is_participant(self, conversation_id: int, user_id: int) -> bool:
        sql = """
            SELECT COUNT(*) AS cnt FROM conversations
            WHERE conversation_id = %s AND (user_a_id = %s OR user_b_id = %s)
        """
        row = self.fetch_one(sql, (conversation_id, user_id, user_id))
        return row["cnt"] > 0 if row else False
