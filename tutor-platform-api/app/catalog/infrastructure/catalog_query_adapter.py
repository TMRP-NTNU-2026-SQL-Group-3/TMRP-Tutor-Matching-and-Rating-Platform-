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

    def tutor_exists(self, tutor_id: int) -> bool:
        row = self.fetch_one("SELECT 1 FROM tutors WHERE tutor_id = %s", (tutor_id,))
        return row is not None

    def tutor_teaches_subject(self, tutor_id: int, subject_id: int) -> bool:
        row = self.fetch_one(
            "SELECT 1 FROM tutor_subjects WHERE tutor_id = %s AND subject_id = %s",
            (tutor_id, subject_id),
        )
        return row is not None

    def get_active_student_count(self, tutor_id: int) -> int:
        row = self.fetch_one(
            "SELECT COUNT(*) AS cnt FROM matches WHERE tutor_id = %s AND status IN ('active', 'trial')",
            (tutor_id,),
        )
        return row["cnt"] if row else 0

    def get_max_students(self, tutor_id: int) -> int:
        row = self.fetch_one("SELECT max_students FROM tutors WHERE tutor_id = %s", (tutor_id,))
        return row["max_students"] if row and row["max_students"] is not None else 5
