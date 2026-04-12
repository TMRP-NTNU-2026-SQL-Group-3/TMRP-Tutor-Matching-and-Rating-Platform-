"""FastAPI dependencies for the admin bounded context."""

from fastapi import Depends

from app.admin.application.import_service import AdminImportService
from app.admin.infrastructure.table_admin_repo import TableAdminRepository
from app.identity.api.dependencies import get_db
from app.shared.infrastructure.postgres_unit_of_work import PostgresUnitOfWork


def get_admin_repo(conn=Depends(get_db)) -> TableAdminRepository:
    return TableAdminRepository(conn)


def get_admin_import_service(conn=Depends(get_db)) -> AdminImportService:
    return AdminImportService(
        repo=TableAdminRepository(conn),
        uow=PostgresUnitOfWork(conn),
    )
