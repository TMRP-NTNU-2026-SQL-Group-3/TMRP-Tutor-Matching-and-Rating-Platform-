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
