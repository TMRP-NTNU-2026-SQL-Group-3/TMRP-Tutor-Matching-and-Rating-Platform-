from app.shared.infrastructure.base_repository import BaseRepository


class PostgresIdempotencyRepository(BaseRepository):

    def find_match_id(self, user_id: int, idem_key: str) -> int | None:
        row = self.fetch_one(
            """SELECT match_id FROM idempotency_keys
               WHERE user_id = %s AND idem_key = %s AND expires_at > NOW()""",
            (user_id, idem_key),
        )
        return int(row["match_id"]) if row else None

    def record(self, idem_key: str, user_id: int, match_id: int) -> None:
        self.execute(
            """INSERT INTO idempotency_keys (idem_key, user_id, match_id, expires_at)
               VALUES (%s, %s, %s, NOW() + INTERVAL '24 hours')
               ON CONFLICT (user_id, idem_key) DO NOTHING""",
            (idem_key, user_id, match_id),
        )
