from pydantic import BaseModel


class StudentCreate(BaseModel):
    name: str
    school: str | None = None
    grade: str | None = None


class StudentUpdate(BaseModel):
    name: str | None = None
    school: str | None = None
    grade: str | None = None
    target_school: str | None = None
