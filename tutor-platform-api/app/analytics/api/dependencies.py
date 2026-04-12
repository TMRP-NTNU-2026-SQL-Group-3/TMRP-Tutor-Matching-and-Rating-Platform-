"""FastAPI dependencies for the analytics bounded context."""

from fastapi import Depends

from app.analytics.application.stats_service import StatsAppService
from app.analytics.infrastructure.postgres_stats_repo import PostgresStatsRepository
from app.identity.api.dependencies import get_db


def get_stats_service(conn=Depends(get_db)) -> StatsAppService:
    return StatsAppService(repo=PostgresStatsRepository(conn))
