from fastapi import APIRouter, Depends

from app.dependencies import get_db
from app.models.common import ApiResponse
from app.repositories.base import BaseRepository

router = APIRouter(prefix="/api/subjects", tags=["subjects"])


@router.get("", summary="列出所有科目", description="取得系統中所有科目的列表，按類別和名稱排序。此 API 不需要登入驗證。", response_model=ApiResponse)
def list_subjects(conn=Depends(get_db)):
    repo = BaseRepository(conn)
    subjects = repo.fetch_all(
        "SELECT * FROM Subjects ORDER BY category, subject_name"
    )
    return ApiResponse(success=True, data=subjects)
