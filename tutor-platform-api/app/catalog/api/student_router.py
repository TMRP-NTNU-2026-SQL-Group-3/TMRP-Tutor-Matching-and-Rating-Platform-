from fastapi import APIRouter, Depends, Query

from app.catalog.api.schemas import StudentCreate, StudentUpdate
from app.catalog.infrastructure.postgres_student_repo import PostgresStudentRepository
from app.identity.api.dependencies import get_db, require_role
from app.shared.api.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.shared.api.schemas import ApiResponse
from app.shared.domain.exceptions import DomainException, NotFoundError

router = APIRouter(prefix="/api/students", tags=["students"])


@router.get("", summary="列出學生", response_model=ApiResponse)
def list_students(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    user=Depends(require_role("parent", "tutor")),
    conn=Depends(get_db),
):
    repo = PostgresStudentRepository(conn)
    user_id = int(user["sub"])
    offset = (page - 1) * page_size
    if user["role"] == "tutor":
        students = repo.find_by_tutor_user_id(user_id, limit=page_size, offset=offset)
        total = repo.count_by_tutor_user_id(user_id)
    else:
        students = repo.find_by_parent(user_id, limit=page_size, offset=offset)
        total = repo.count_by_parent(user_id)
    total_pages = max(1, (total + page_size - 1) // page_size)
    return ApiResponse(
        success=True,
        data={
            "items": students,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    )


_MAX_STUDENTS_PER_PARENT = 20


@router.post("", summary="新增子女", response_model=ApiResponse)
def add_student(body: StudentCreate, user=Depends(require_role("parent")), conn=Depends(get_db)):
    # Name trimming / empty-check is handled by TrimmedStr in StudentCreate.
    repo = PostgresStudentRepository(conn)
    parent_id = int(user["sub"])
    if repo.count_by_parent(parent_id) >= _MAX_STUDENTS_PER_PARENT:
        raise DomainException(f"每位家長最多新增 {_MAX_STUDENTS_PER_PARENT} 名子女")
    student_id = repo.create(
        parent_user_id=parent_id,
        name=body.name,
        school=body.school,
        grade=body.grade,
    )
    return ApiResponse(success=True, data={"student_id": student_id}, message="新增成功")


@router.put("/{student_id}", summary="更新子女資料", response_model=ApiResponse)
def update_student(student_id: int, body: StudentUpdate, user=Depends(require_role("parent")), conn=Depends(get_db)):
    repo = PostgresStudentRepository(conn)
    # SEC-09: ownership enforced in the SQL predicate; returns None for both
    # "not found" and "not owned", so callers cannot probe other users' IDs.
    student = repo.find_by_id_for_parent(student_id, int(user["sub"]))
    if not student:
        raise NotFoundError("找不到此學生")
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise DomainException("沒有提供任何要更新的欄位")
    repo.update(student_id, updates)
    return ApiResponse(success=True, data={"student_id": student_id}, message="學生資料已更新")


@router.delete("/{student_id}", summary="刪除子女資料", response_model=ApiResponse)
def delete_student(student_id: int, user=Depends(require_role("parent")), conn=Depends(get_db)):
    repo = PostgresStudentRepository(conn)
    # SEC-09: ownership enforced in the SQL predicate (see update_student note).
    student = repo.find_by_id_for_parent(student_id, int(user["sub"]))
    if not student:
        raise NotFoundError("找不到此學生")
    repo.delete(student_id)
    return ApiResponse(success=True, data={"student_id": student_id}, message="學生資料已刪除")
