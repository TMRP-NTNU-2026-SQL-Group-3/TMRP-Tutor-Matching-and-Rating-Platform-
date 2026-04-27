from abc import ABC, abstractmethod


class IUserRepository(ABC):

    @abstractmethod
    def find_by_username(self, username: str) -> dict | None: ...

    @abstractmethod
    def find_by_id(self, user_id: int) -> dict | None: ...

    @abstractmethod
    def register_user(
        self, username: str, password_hash: str, display_name: str,
        role: str, phone: str | None, email: str | None,
    ) -> int: ...

    @abstractmethod
    def update_me(self, user_id: int, *, fields: dict) -> None: ...

    @abstractmethod
    def update_password(self, user_id: int, *, password_hash: str) -> None: ...

    @abstractmethod
    def save_password_history(self, user_id: int, password_hash: str) -> None: ...

    @abstractmethod
    def get_recent_password_hashes(self, user_id: int, limit: int = 5) -> list[str]: ...
