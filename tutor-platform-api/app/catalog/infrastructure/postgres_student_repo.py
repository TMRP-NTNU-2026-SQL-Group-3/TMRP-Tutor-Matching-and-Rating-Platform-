from app.catalog.domain.ports import IStudentRepository
from app.shared.infrastructure.base_repository import BaseRepository


class PostgresStudentRepository(BaseRepository, IStudentRepository):

    def find_by_parent(self, parent_user_id: int) -> list[dict]:
        return self.fetch_all("SELECT * FROM students WHERE parent_user_id = %s ORDER BY student_id", (parent_user_id,))

    def find_by_id(self, student_id: int) -> dict | None:
        return self.fetch_one("SELECT * FROM students WHERE student_id = %s", (student_id,))

    def create(self, parent_user_id: int, name: str, school: str | None = None, grade: str | None = None) -> int:
        return self.execute_returning_id(
            "INSERT INTO students (parent_user_id, name, school, grade) VALUES (%s, %s, %s, %s) RETURNING student_id",
            (parent_user_id, name, school, grade),
        )

    ALLOWED_COLUMNS = {"name", "school", "grade", "target_school", "parent_phone", "notes"}

    def update(self, student_id: int, updates: dict) -> None:
        self.safe_update("students", "student_id", student_id, updates, self.ALLOWED_COLUMNS)
