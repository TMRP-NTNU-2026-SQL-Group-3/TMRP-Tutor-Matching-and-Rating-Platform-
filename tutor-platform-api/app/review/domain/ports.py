from abc import ABC, abstractmethod


class IReviewRepository(ABC):
    @abstractmethod
    def get_match_for_create(self, match_id: int) -> dict | None: ...

    @abstractmethod
    def get_match_participants(self, match_id: int) -> dict | None: ...

    @abstractmethod
    def find_existing(self, match_id: int, reviewer_user_id: int, review_type: str) -> dict | None: ...

    @abstractmethod
    def create(self, match_id, reviewer_user_id, review_type, rating_1, rating_2, rating_3, rating_4, personality_comment, comment) -> int: ...

    @abstractmethod
    def list_by_match(self, match_id: int) -> list[dict]: ...

    @abstractmethod
    def list_by_tutor(
        self, tutor_id: int, *, limit: int = 20, offset: int = 0,
    ) -> list[dict]: ...

    @abstractmethod
    def get_for_update(self, review_id: int) -> dict | None: ...

    @abstractmethod
    def update(self, review_id: int, updates: dict) -> None: ...
