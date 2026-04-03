from fastapi import APIRouter, Depends

from app.dependencies import get_db, require_role
from app.exceptions import AppException, ForbiddenException, NotFoundException
from app.models.common import ApiResponse
from app.models.student import StudentCreate, StudentUpdate
from app.repositories.student_repo import StudentRepository

router = APIRouter(prefix="/api/students", tags=["students"])


@router.get("", response_model=ApiResponse)
def list_students(user=Depends(require_role("parent")), conn=Depends(get_db)):
    repo = StudentRepository(conn)
    students = repo.find_by_parent(int(user["sub"]))
    return ApiResponse(success=True, data=students)


@router.post("", response_model=ApiResponse)
def add_student(
    body: StudentCreate,
    user=Depends(require_role("parent")),
    conn=Depends(get_db),
):
    if not body.name or not body.name.strip():
        raise AppException("子女姓名不可為空")
    repo = StudentRepository(conn)
    student_id = repo.create(
        parent_user_id=int(user["sub"]),
        name=body.name.strip(),
        school=body.school,
        grade=body.grade,
    )
    return ApiResponse(success=True, data={"student_id": student_id}, message="新增成功")


@router.put("/{student_id}", response_model=ApiResponse)
def update_student(
    student_id: int,
    body: StudentUpdate,
    user=Depends(require_role("parent")),
    conn=Depends(get_db),
):
    """修改子女資料（僅限家長本人）。"""
    repo = StudentRepository(conn)
    student = repo.find_by_id(student_id)
    if not student:
        raise NotFoundException("找不到此學生")
    if student["parent_user_id"] != int(user["sub"]):
        raise ForbiddenException("只能修改自己的子女資料")

    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    if not updates:
        raise AppException("沒有提供任何要更新的欄位")

    repo.update(student_id, updates)
    return ApiResponse(success=True, data={"student_id": student_id}, message="學生資料已更新")
