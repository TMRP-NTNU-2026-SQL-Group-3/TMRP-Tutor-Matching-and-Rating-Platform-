from app.repositories.base import BaseRepository


class StudentRepository(BaseRepository):

    def find_by_parent(self, parent_user_id: int) -> list[dict]:
        sql = "SELECT * FROM students WHERE parent_user_id = %s ORDER BY student_id"
        return self.fetch_all(sql, (parent_user_id,))

    def find_by_id(self, student_id: int) -> dict | None:
        sql = "SELECT * FROM students WHERE student_id = %s"
        return self.fetch_one(sql, (student_id,))

    def create(
        self,
        parent_user_id: int,
        name: str,
        school: str | None = None,
        grade: str | None = None,
    ) -> int:
        sql = """
            INSERT INTO students (parent_user_id, name, school, grade)
            VALUES (%s, %s, %s, %s)
            RETURNING student_id
        """
        return self.execute_returning_id(sql, (parent_user_id, name, school, grade))

    # P-API-01: 加入 target_school, parent_phone, notes 等欄位
    ALLOWED_COLUMNS = {"name", "school", "grade", "target_school", "parent_phone", "notes"}

    def update(self, student_id: int, updates: dict) -> None:
        self.safe_update("students", "student_id", student_id, updates, self.ALLOWED_COLUMNS)
