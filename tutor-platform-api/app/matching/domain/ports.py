from abc import ABC, abstractmethod

from .entities import Match


class IMatchRepository(ABC):
    @abstractmethod
    def find_by_id(self, match_id: int) -> Match | None: ...

    @abstractmethod
    def find_by_tutor_user_id(self, user_id: int) -> list[dict]: ...

    @abstractmethod
    def find_by_parent_user_id(self, user_id: int) -> list[dict]: ...

    @abstractmethod
    def find_all(self) -> list[dict]: ...

    @abstractmethod
    def create(self, tutor_id: int, student_id: int, subject_id: int,
               hourly_rate: float, sessions_per_week: int,
               want_trial: bool, invite_message: str | None) -> int: ...

    @abstractmethod
    def update_status(self, match_id: int, new_status: str) -> None: ...

    @abstractmethod
    def set_terminating(self, match_id: int, user_id: int,
                        reason: str, previous_status: str) -> None: ...

    @abstractmethod
    def clear_termination(self, match_id: int, revert_status: str) -> None: ...

    @abstractmethod
    def check_duplicate_active(self, tutor_id: int,
                               student_id: int, subject_id: int) -> bool: ...


class ICatalogQuery(ABC):
    @abstractmethod
    def get_student_owner(self, student_id: int) -> int | None: ...

    @abstractmethod
    def get_student_owner_for_update(self, student_id: int) -> int | None: ...

    @abstractmethod
    def tutor_exists(self, tutor_id: int) -> bool: ...

    @abstractmethod
    def tutor_teaches_subject(self, tutor_id: int, subject_id: int) -> bool: ...

    @abstractmethod
    def get_active_student_count(self, tutor_id: int) -> int: ...

    @abstractmethod
    def get_max_students(self, tutor_id: int) -> int: ...
