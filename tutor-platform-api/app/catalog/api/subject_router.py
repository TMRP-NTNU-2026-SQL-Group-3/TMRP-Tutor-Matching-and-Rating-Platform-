from fastapi import APIRouter, Depends

from app.identity.api.dependencies import get_db
from app.shared.api.schemas import ApiResponse
from app.shared.infrastructure.base_repository import BaseRepository

router = APIRouter(prefix="/api/subjects", tags=["subjects"])


@router.get("", summary="列出所有科目", response_model=ApiResponse)
def list_subjects(conn=Depends(get_db)):
    repo = BaseRepository(conn)
    subjects = repo.fetch_all("SELECT * FROM subjects ORDER BY category, subject_name")
    return ApiResponse(success=True, data=subjects)
