from fastapi import APIRouter, Depends, Query

from app.identity.api.dependencies import get_db
from app.shared.api.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.shared.api.schemas import ApiResponse
from app.shared.infrastructure.base_repository import BaseRepository

router = APIRouter(prefix="/api/subjects", tags=["subjects"])


@router.get("", summary="列出所有科目", response_model=ApiResponse)
def list_subjects(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    conn=Depends(get_db),
):
    repo = BaseRepository(conn)
    offset = (page - 1) * page_size
    subjects = repo.fetch_all(
        "SELECT * FROM subjects ORDER BY category, subject_name LIMIT %s OFFSET %s",
        (page_size, offset),
    )
    total_row = repo.fetch_one("SELECT COUNT(*) AS cnt FROM subjects")
    total = int(total_row["cnt"]) if total_row else 0
    total_pages = max(1, (total + page_size - 1) // page_size)
    return ApiResponse(
        success=True,
        data={
            "items": subjects,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    )
