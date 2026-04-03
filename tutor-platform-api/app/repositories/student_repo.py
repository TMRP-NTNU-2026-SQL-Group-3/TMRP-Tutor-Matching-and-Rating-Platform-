from app.repositories.base import BaseRepository


class StudentRepository(BaseRepository):

    def find_by_parent(self, parent_user_id: int) -> list[dict]:
        sql = "SELECT * FROM Students WHERE parent_user_id = ? ORDER BY student_id"
        return self.fetch_all(sql, (parent_user_id,))

    def find_by_id(self, student_id: int) -> dict | None:
        sql = "SELECT * FROM Students WHERE student_id = ?"
        return self.fetch_one(sql, (student_id,))

    def create(
        self,
        parent_user_id: int,
        name: str,
        school: str | None = None,
        grade: str | None = None,
    ) -> int:
        sql = """
            INSERT INTO Students (parent_user_id, name, school, grade)
            VALUES (?, ?, ?, ?)
        """
        return self.execute_returning_id(sql, (parent_user_id, name, school, grade))

    def update(self, student_id: int, updates: dict) -> None:
        set_clause = ", ".join(f"{col} = ?" for col in updates)
        values = list(updates.values()) + [student_id]
        self.execute(
            f"UPDATE Students SET {set_clause} WHERE student_id = ?",
            values,
        )
