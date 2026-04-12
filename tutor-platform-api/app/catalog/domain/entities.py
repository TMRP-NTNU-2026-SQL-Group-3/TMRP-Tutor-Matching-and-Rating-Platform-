from dataclasses import dataclass


@dataclass
class Tutor:
    tutor_id: int
    user_id: int
    university: str | None = None
    department: str | None = None
    grade_year: int | None = None
    self_intro: str | None = None
    teaching_experience: str | None = None
    max_students: int = 5
    show_university: bool = True
    show_department: bool = True
    show_grade_year: bool = True
    show_hourly_rate: bool = True
    show_subjects: bool = True
    display_name: str | None = None
    email: str | None = None
    phone: str | None = None


@dataclass
class Student:
    student_id: int
    parent_user_id: int
    name: str
    school: str | None = None
    grade: str | None = None
    target_school: str | None = None
    parent_phone: str | None = None
    notes: str | None = None
