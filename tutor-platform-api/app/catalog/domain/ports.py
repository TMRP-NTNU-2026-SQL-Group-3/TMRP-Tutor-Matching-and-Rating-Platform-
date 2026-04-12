from abc import ABC, abstractmethod


class ITutorRepository(ABC):
    @abstractmethod
    def search(self, subject_id: int | None = None, school: str | None = None) -> list[dict]: ...

    @abstractmethod
    def find_by_id(self, tutor_id: int) -> dict | None: ...

    @abstractmethod
    def find_by_user_id(self, user_id: int) -> dict | None: ...

    @abstractmethod
    def get_subjects(self, tutor_id: int) -> list[dict]: ...

    @abstractmethod
    def get_availability(self, tutor_id: int) -> list[dict]: ...

    @abstractmethod
    def get_avg_rating(self, tutor_id: int) -> dict | None: ...

    @abstractmethod
    def get_active_student_count(self, tutor_id: int) -> int: ...

    @abstractmethod
    def replace_subjects(self, tutor_id: int, items: list[dict]) -> None: ...

    @abstractmethod
    def replace_availability(self, tutor_id: int, slots: list[dict]) -> None: ...

    @abstractmethod
    def update_visibility(self, tutor_id: int, flags: dict) -> None: ...

    @abstractmethod
    def update_profile(self, tutor_id: int, **fields) -> None: ...


class IStudentRepository(ABC):
    @abstractmethod
    def find_by_parent(self, parent_user_id: int) -> list[dict]: ...

    @abstractmethod
    def find_by_id(self, student_id: int) -> dict | None: ...

    @abstractmethod
    def create(self, parent_user_id: int, name: str, school: str | None = None, grade: str | None = None) -> int: ...

    @abstractmethod
    def update(self, student_id: int, updates: dict) -> None: ...
