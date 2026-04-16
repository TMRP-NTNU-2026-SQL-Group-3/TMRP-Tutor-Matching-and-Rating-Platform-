from app.catalog.domain.constants import DEFAULT_MAX_STUDENTS_PER_TUTOR
from app.matching.domain.ports import ICatalogQuery
from app.shared.infrastructure.base_repository import BaseRepository


class CatalogQueryAdapter(BaseRepository, ICatalogQuery):

    def get_student_owner(self, student_id: int) -> int | None:
        row = self.fetch_one("SELECT parent_user_id FROM students WHERE student_id = %s", (student_id,))
        return row["parent_user_id"] if row else None

    def get_student_owner_for_update(self, student_id: int) -> int | None:
        row = self.fetch_one(
            "SELECT parent_user_id FROM students WHERE student_id = %s FOR UPDATE",
            (student_id,),
        )
        return row["parent_user_id"] if row else None

    def lock_tutor_for_update(self, tutor_id: int) -> bool:
        """Acquire a row-level lock on the tutor. Required before reading the
        capacity counts so two concurrent create_match calls cannot both pass
        the (active < max_students) check."""
        row = self.fetch_one(
            "SELECT 1 FROM tutors WHERE tutor_id = %s FOR UPDATE",
            (tutor_id,),
        )
        return row is not None

    def tutor_teaches_subject(self, tutor_id: int, subject_id: int) -> bool:
        row = self.fetch_one(
            "SELECT 1 FROM tutor_subjects WHERE tutor_id = %s AND subject_id = %s",
            (tutor_id, subject_id),
        )
        return row is not None

    def get_active_student_count(self, tutor_id: int) -> int:
        # DB-H01: count all non-terminal matches directly from the matches
        # table instead of v_tutor_active_students (which only counts
        # active/trial).  Including pending/paused/terminating ensures the
        # FOR UPDATE lock on the tutor row (acquired earlier in the same tx)
        # actually prevents two concurrent create_match calls from both
        # passing the capacity gate — a pending INSERT now "reserves" a slot.
        row = self.fetch_one(
            """SELECT COUNT(*) AS cnt FROM matches
               WHERE tutor_id = %s
                 AND status NOT IN ('cancelled', 'rejected', 'ended')""",
            (tutor_id,),
        )
        return row["cnt"] if row else 0

    def get_max_students(self, tutor_id: int) -> int:
        row = self.fetch_one("SELECT max_students FROM tutors WHERE tutor_id = %s", (tutor_id,))
        return row["max_students"] if row and row["max_students"] is not None else DEFAULT_MAX_STUDENTS_PER_TUTOR
