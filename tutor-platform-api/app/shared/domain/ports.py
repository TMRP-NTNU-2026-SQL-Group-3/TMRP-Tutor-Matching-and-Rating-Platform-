from abc import ABC, abstractmethod
from contextlib import AbstractContextManager


class IUnitOfWork(ABC):
    """Transaction boundary port. Implementations scope a single atomic unit;
    nested `begin()` calls pass through to the outermost transaction."""

    @abstractmethod
    def begin(self) -> AbstractContextManager: ...
