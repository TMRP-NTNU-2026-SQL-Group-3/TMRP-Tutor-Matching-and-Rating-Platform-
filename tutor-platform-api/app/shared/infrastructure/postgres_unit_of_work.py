from contextlib import AbstractContextManager

from app.shared.domain.ports import IUnitOfWork
from app.shared.infrastructure.database_tx import transaction


class PostgresUnitOfWork(IUnitOfWork):
    """Psycopg2-backed UnitOfWork. Wraps the shared `transaction()` helper
    so application services never touch the raw connection directly."""

    def __init__(self, conn):
        self._conn = conn

    def begin(self) -> AbstractContextManager:
        return transaction(self._conn)

    def __enter__(self):
        self._ctx = self.begin()
        return self._ctx.__enter__()

    def __exit__(self, exc_type, exc, tb):
        return self._ctx.__exit__(exc_type, exc, tb)
