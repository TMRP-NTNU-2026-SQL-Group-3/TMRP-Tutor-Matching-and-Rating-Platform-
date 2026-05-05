"""FastAPI dependencies for the teaching bounded context."""

from fastapi import Depends

from app.identity.api.dependencies import get_db
from app.shared.infrastructure.postgres_unit_of_work import PostgresUnitOfWork
from app.teaching.application.exam_service import ExamAppService
from app.teaching.application.session_service import SessionAppService
from app.teaching.infrastructure.postgres_exam_repo import PostgresExamRepository
from app.teaching.infrastructure.postgres_session_repo import PostgresSessionRepository


def get_session_service(conn=Depends(get_db)) -> SessionAppService:
    return SessionAppService(
        repo=PostgresSessionRepository(conn),
        uow=PostgresUnitOfWork(conn),
    )


def get_exam_service(conn=Depends(get_db)) -> ExamAppService:
    return ExamAppService(repo=PostgresExamRepository(conn))
