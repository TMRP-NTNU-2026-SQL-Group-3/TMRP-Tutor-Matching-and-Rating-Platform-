from pydantic import BaseModel, Field


class TutorProfileUpdate(BaseModel):
    self_intro: str | None = None
    teaching_experience: str | None = None
    university: str | None = None
    department: str | None = None
    grade_year: int | None = None
    max_students: int | None = None
    show_university: bool = True
    show_department: bool = True
    show_grade_year: bool = True
    show_hourly_rate: bool = True
    show_subjects: bool = True


class AvailabilitySlot(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    start_time: str
    end_time: str


class AvailabilityUpdate(BaseModel):
    slots: list[AvailabilitySlot]


class VisibilityUpdate(BaseModel):
    show_university: bool | None = None
    show_department: bool | None = None
    show_grade_year: bool | None = None
    show_hourly_rate: bool | None = None
    show_subjects: bool | None = None
