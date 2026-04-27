from app.catalog.domain.ports import IStudentRepository
from app.shared.infrastructure.base_repository import BaseRepository


class PostgresStudentRepository(BaseRepository, IStudentRepository):

    def find_by_parent(self, parent_user_id: int, limit: int = 100, offset: int = 0) -> list[dict]:
        return self.fetch_all(
            "SELECT * FROM students WHERE parent_user_id = %s ORDER BY student_id LIMIT %s OFFSET %s",
            (parent_user_id, limit, offset),
        )

    def count_by_parent(self, parent_user_id: int) -> int:
        row = self.fetch_one("SELECT COUNT(*) AS cnt FROM students WHERE parent_user_id = %s", (parent_user_id,))
        return int(row["cnt"]) if row else 0

    def find_by_id(self, student_id: int) -> dict | None:
        return self.fetch_one("SELECT * FROM students WHERE student_id = %s", (student_id,))

    def find_by_id_for_parent(self, student_id: int, parent_user_id: int) -> dict | None:
        """SEC-09: ownership enforced at the DB layer as well as in application code."""
        return self.fetch_one(
            "SELECT * FROM students WHERE student_id = %s AND parent_user_id = %s",
            (student_id, parent_user_id),
        )

    def create(self, parent_user_id: int, name: str, school: str | None = None, grade: str | None = None) -> int:
        return self.execute_returning_id(
            "INSERT INTO students (parent_user_id, name, school, grade) VALUES (%s, %s, %s, %s) RETURNING student_id",
            (parent_user_id, name, school, grade),
        )

    ALLOWED_COLUMNS = {"name", "school", "grade", "target_school", "parent_phone", "notes"}

    def update(self, student_id: int, updates: dict) -> None:
        self.safe_update("students", "student_id", student_id, updates, self.ALLOWED_COLUMNS)

    def delete(self, student_id: int) -> bool:
        self.execute(
            "DELETE FROM students WHERE student_id = %s",
            (student_id,),
        )
        return self.cursor.rowcount > 0
