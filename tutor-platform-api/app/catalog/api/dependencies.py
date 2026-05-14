"""FastAPI dependencies for the catalog bounded context."""

from fastapi import Depends

from app.catalog.domain.services import TutorService
from app.catalog.infrastructure.postgres_subject_repo import PostgresSubjectRepository
from app.catalog.infrastructure.postgres_tutor_repo import PostgresTutorRepository
from app.identity.api.dependencies import get_db


def get_tutor_repo(conn=Depends(get_db)) -> PostgresTutorRepository:
    return PostgresTutorRepository(conn)


def get_subject_repo(conn=Depends(get_db)) -> PostgresSubjectRepository:
    return PostgresSubjectRepository(conn)


def get_tutor_service(
    repo: PostgresTutorRepository = Depends(get_tutor_repo),
) -> TutorService:
    return TutorService(tutor_repo=repo)
