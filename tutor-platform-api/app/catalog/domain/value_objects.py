from dataclasses import dataclass


@dataclass(frozen=True)
class AvailabilitySlot:
    day_of_week: int      # 1-7 (1=Monday, 7=Sunday, per spec §6.2.6)
    start_time: str       # "HH:MM"
    end_time: str         # "HH:MM"


@dataclass(frozen=True)
class SubjectRate:
    subject_id: int
    subject_name: str
    hourly_rate: float


@dataclass(frozen=True)
class Visibility:
    show_university: bool = True
    show_department: bool = True
    show_grade_year: bool = True
    show_hourly_rate: bool = True
    show_subjects: bool = True
