from psycopg2 import sql as psql

from app.matching.domain.entities import Match
from app.matching.domain.ports import IMatchRepository
from app.matching.domain.value_objects import Contract, MatchStatus
from app.shared.infrastructure.base_repository import BaseRepository


class PostgresMatchRepository(BaseRepository, IMatchRepository):

    def _row_to_entity(self, row: dict) -> Match:
        return Match(
            match_id=row["match_id"],
            tutor_id=row["tutor_id"],
            student_id=row["student_id"],
            subject_id=row["subject_id"],
            status=MatchStatus(row["status"]),
            contract=Contract(
                hourly_rate=float(row.get("hourly_rate") or 0),
                sessions_per_week=int(row.get("sessions_per_week") or 0),
                want_trial=bool(row.get("want_trial")),
                invite_message=row.get("invite_message"),
                start_date=row.get("start_date"),
                end_date=row.get("end_date"),
                penalty_amount=float(row["penalty_amount"]) if row.get("penalty_amount") is not None else None,
                trial_price=float(row["trial_price"]) if row.get("trial_price") is not None else None,
                trial_count=int(row["trial_count"]) if row.get("trial_count") is not None else None,
                contract_notes=row.get("contract_notes"),
            ),
            terminated_by=row.get("terminated_by"),
            termination_reason=row.get("termination_reason"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            subject_name=row.get("subject_name"),
            student_name=row.get("student_name"),
            parent_user_id=row.get("parent_user_id"),
            tutor_user_id=row.get("tutor_user_id"),
            tutor_display_name=row.get("tutor_display_name"),
        )

    def find_by_id(self, match_id: int) -> Match | None:
        row = self.fetch_one(
            """SELECT m.*, s.subject_name,
                      st.name AS student_name, st.parent_user_id,
                      t.user_id AS tutor_user_id,
                      u.display_name AS tutor_display_name
               FROM matches m
               INNER JOIN subjects s ON m.subject_id = s.subject_id
               INNER JOIN students st ON m.student_id = st.student_id
               INNER JOIN tutors t ON m.tutor_id = t.tutor_id
               INNER JOIN users u ON t.user_id = u.user_id
               WHERE m.match_id = %s""",
            (match_id,),
        )
        return self._row_to_entity(row) if row else None

    def find_by_tutor_user_id(self, user_id: int) -> list[dict]:
        return self.fetch_all(
            """SELECT m.*, s.subject_name, st.name AS student_name
               FROM matches m
               INNER JOIN subjects s ON m.subject_id = s.subject_id
               INNER JOIN students st ON m.student_id = st.student_id
               INNER JOIN tutors t ON m.tutor_id = t.tutor_id
               WHERE t.user_id = %s ORDER BY m.updated_at DESC""",
            (user_id,),
        )

    def find_by_parent_user_id(self, user_id: int) -> list[dict]:
        return self.fetch_all(
            """SELECT m.*, s.subject_name, st.name AS student_name,
                      u.display_name AS tutor_display_name
               FROM matches m
               INNER JOIN subjects s ON m.subject_id = s.subject_id
               INNER JOIN students st ON m.student_id = st.student_id
               INNER JOIN tutors t ON m.tutor_id = t.tutor_id
               INNER JOIN users u ON t.user_id = u.user_id
               WHERE st.parent_user_id = %s ORDER BY m.updated_at DESC""",
            (user_id,),
        )

    def find_all(self) -> list[dict]:
        return self.fetch_all(
            """SELECT m.*, s.subject_name, st.name AS student_name
               FROM matches m
               INNER JOIN subjects s ON m.subject_id = s.subject_id
               INNER JOIN students st ON m.student_id = st.student_id
               ORDER BY m.updated_at DESC"""
        )

    def create(self, tutor_id, student_id, subject_id, hourly_rate,
               sessions_per_week, want_trial, invite_message) -> int:
        return self.execute_returning_id(
            """INSERT INTO matches
                (tutor_id, student_id, subject_id, status,
                 hourly_rate, sessions_per_week, want_trial,
                 invite_message, created_at, updated_at)
               VALUES (%s, %s, %s, 'pending', %s, %s, %s, %s, NOW(), NOW())
               RETURNING match_id""",
            (tutor_id, student_id, subject_id,
             hourly_rate, sessions_per_week, want_trial, invite_message),
        )

    VALID_STATUSES = {'pending', 'trial', 'active', 'paused', 'cancelled',
                      'rejected', 'terminating', 'ended'}

    def update_status(self, match_id: int, new_status: str) -> None:
        if new_status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid status: {new_status}")
        self.execute(
            "UPDATE matches SET status = %s, updated_at = NOW() WHERE match_id = %s",
            (new_status, match_id),
        )

    def confirm_trial_with_terms(
        self, *, match_id: int, new_status: str,
        hourly_rate: float | None,
        sessions_per_week: int | None,
        start_date: object | None,
    ) -> None:
        # Used by the trial → active confirmation flow (Spec Module D). Only
        # fields the user actually provided are written, so callers can edit
        # any subset of the contract terms.
        if new_status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid status: {new_status}")
        # Build the SET clause through psycopg2.sql.Composable so column names
        # are always identifier-quoted by the driver rather than interpolated
        # as raw strings. Today the field names are hard-coded literals, so
        # the f-string variant is safe — but the Composable form removes any
        # possibility of a future refactor accidentally feeding a caller-
        # controlled key into the SQL fragment.
        set_parts = [
            psql.SQL("{} = {}").format(psql.Identifier("status"), psql.Placeholder()),
            psql.SQL("{} = NOW()").format(psql.Identifier("updated_at")),
        ]
        params: list = [new_status]
        optional_fields: list[tuple[str, object]] = []
        if hourly_rate is not None:
            optional_fields.append(("hourly_rate", hourly_rate))
        if sessions_per_week is not None:
            optional_fields.append(("sessions_per_week", sessions_per_week))
        if start_date is not None:
            optional_fields.append(("start_date", start_date))
        for col, val in optional_fields:
            set_parts.append(
                psql.SQL("{} = {}").format(psql.Identifier(col), psql.Placeholder())
            )
            params.append(val)
        params.append(match_id)
        query = psql.SQL("UPDATE {} SET {} WHERE {} = {}").format(
            psql.Identifier("matches"),
            psql.SQL(", ").join(set_parts),
            psql.Identifier("match_id"),
            psql.Placeholder(),
        )
        self.execute(query.as_string(self.conn), tuple(params))

    # Hard ceiling on the combined "{previous_status}|{reason}" payload that
    # `clear_termination` later reverses by splitting on "|". A bad-actor
    # reason would otherwise stuff the column past any UI display limit and
    # — if the underlying column is later narrowed from TEXT — silently
    # truncate to a value the splitter cannot recover.
    _MAX_TERMINATION_REASON_CHARS = 1000

    def set_terminating(self, match_id, user_id, reason, previous_status) -> None:
        if reason is not None and len(reason) > self._MAX_TERMINATION_REASON_CHARS:
            raise ValueError(
                f"termination reason exceeds {self._MAX_TERMINATION_REASON_CHARS} chars"
            )
        combined_reason = f"{previous_status}|{reason}" if reason else previous_status
        self.execute(
            """UPDATE matches SET status = 'terminating', terminated_by = %s,
                      termination_reason = %s, updated_at = NOW()
               WHERE match_id = %s""",
            (user_id, combined_reason, match_id),
        )

    def clear_termination(self, match_id, revert_status) -> None:
        self.execute(
            """UPDATE matches SET status = %s, terminated_by = NULL,
                      termination_reason = NULL, updated_at = NOW()
               WHERE match_id = %s""",
            (revert_status, match_id),
        )

    def check_duplicate_active(self, tutor_id, student_id, subject_id) -> bool:
        row = self.fetch_one(
            """SELECT COUNT(*) AS cnt FROM matches
               WHERE tutor_id = %s AND student_id = %s AND subject_id = %s
               AND status NOT IN ('cancelled', 'rejected', 'ended')""",
            (tutor_id, student_id, subject_id),
        )
        return row["cnt"] > 0 if row else False

    def record_admin_transition(
        self, *, match_id: int, actor_user_id: int,
        action: str, old_status: str, new_status: str,
        reason: str | None,
    ) -> None:
        """B10: persist an audit row for an admin-initiated match transition.
        Written through `execute`, which participates in the caller's tx when
        one is open, so the audit is committed atomically with the status
        flip (or rolled back together on failure)."""
        # DB-L04: resource_id is a soft reference (no FK) — the referenced
        # row (here: match_id) may be deleted independently. Consuming code
        # must tolerate dangling resource_id values when joining back.
        self.execute(
            """INSERT INTO audit_log
                (actor_user_id, action, resource_type, resource_id,
                 old_value, new_value, reason)
               VALUES (%s, %s, 'match', %s, %s, %s, %s)""",
            (actor_user_id, action, match_id, old_status, new_status, reason),
        )
