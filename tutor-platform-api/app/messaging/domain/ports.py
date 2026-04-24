from abc import ABC, abstractmethod


class IConversationRepository(ABC):
    @abstractmethod
    def find_conversations_for_user(self, user_id: int) -> list[dict]: ...

    @abstractmethod
    def get_or_create_conversation(self, user_a_id: int, user_b_id: int) -> int: ...

    @abstractmethod
    def user_is_participant(self, conversation_id: int, user_id: int) -> bool: ...


class IMessageRepository(ABC):
    @abstractmethod
    def get_messages(self, conversation_id: int, *, limit: int, before_id: int | None = None) -> list[dict]: ...

    @abstractmethod
    def send_message(self, conversation_id: int, sender_user_id: int, content: str) -> int: ...

    @abstractmethod
    def message_in_conversation(self, message_id: int, conversation_id: int) -> bool: ...
