from fastapi import APIRouter, Depends

from app.catalog.api.schemas import StudentCreate, StudentUpdate
from app.catalog.infrastructure.postgres_student_repo import PostgresStudentRepository
from app.identity.api.dependencies import get_db, require_role
from app.shared.api.schemas import ApiResponse
from app.shared.domain.exceptions import DomainException, NotFoundError, PermissionDeniedError

router = APIRouter(prefix="/api/students", tags=["students"])


@router.get("", summary="列出我的子女", response_model=ApiResponse)
def list_students(user=Depends(require_role("parent")), conn=Depends(get_db)):
    repo = PostgresStudentRepository(conn)
    students = repo.find_by_parent(int(user["sub"]))
    return ApiResponse(success=True, data=students)


@router.post("", summary="新增子女", response_model=ApiResponse)
def add_student(body: StudentCreate, user=Depends(require_role("parent")), conn=Depends(get_db)):
    if not body.name or not body.name.strip():
        raise DomainException("子女姓名不可為空")
    repo = PostgresStudentRepository(conn)
    student_id = repo.create(
        parent_user_id=int(user["sub"]),
        name=body.name.strip(),
        school=body.school,
        grade=body.grade,
    )
    return ApiResponse(success=True, data={"student_id": student_id}, message="新增成功")


@router.put("/{student_id}", summary="更新子女資料", response_model=ApiResponse)
def update_student(student_id: int, body: StudentUpdate, user=Depends(require_role("parent")), conn=Depends(get_db)):
    repo = PostgresStudentRepository(conn)
    student = repo.find_by_id(student_id)
    if not student:
        raise NotFoundError("找不到此學生")
    if student["parent_user_id"] != int(user["sub"]):
        raise PermissionDeniedError("只能修改自己的子女資料")
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise DomainException("沒有提供任何要更新的欄位")
    repo.update(student_id, updates)
    return ApiResponse(success=True, data={"student_id": student_id}, message="學生資料已更新")
