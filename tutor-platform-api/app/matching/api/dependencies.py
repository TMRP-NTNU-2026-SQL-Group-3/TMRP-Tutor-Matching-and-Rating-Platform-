"""FastAPI dependencies for the matching bounded context."""

from fastapi import Depends

from app.catalog.infrastructure.catalog_query_adapter import CatalogQueryAdapter
from app.identity.api.dependencies import get_db
from app.matching.application.match_app_service import MatchAppService
from app.matching.infrastructure.postgres_idempotency_repo import PostgresIdempotencyRepository
from app.matching.infrastructure.postgres_match_repo import PostgresMatchRepository
from app.matching.infrastructure.postgres_unit_of_work import PostgresUnitOfWork


def get_match_service(conn=Depends(get_db)) -> MatchAppService:
    return MatchAppService(
        match_repo=PostgresMatchRepository(conn),
        catalog=CatalogQueryAdapter(conn),
        uow=PostgresUnitOfWork(conn),
    )


def get_idempotency_repo(conn=Depends(get_db)) -> PostgresIdempotencyRepository:
    return PostgresIdempotencyRepository(conn)
