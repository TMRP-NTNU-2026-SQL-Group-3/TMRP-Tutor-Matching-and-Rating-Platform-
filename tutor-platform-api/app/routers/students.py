from fastapi import APIRouter, Depends

from app.dependencies import get_db, require_role
from app.exceptions import AppException, ForbiddenException, NotFoundException
from app.models.common import ApiResponse
from app.models.student import StudentCreate, StudentUpdate
from app.repositories.student_repo import StudentRepository

router = APIRouter(prefix="/api/students", tags=["students"])


@router.get("", summary="列出我的子女", description="列出目前登入家長的所有子女資料。僅限家長角色。", response_model=ApiResponse)
def list_students(user=Depends(require_role("parent")), conn=Depends(get_db)):
    repo = StudentRepository(conn)
    students = repo.find_by_parent(int(user["sub"]))
    return ApiResponse(success=True, data=students)


@router.post("", summary="新增子女", description="為目前登入的家長新增一位子女，姓名為必填欄位。", response_model=ApiResponse)
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


@router.put("/{student_id}", summary="更新子女資料", description="修改指定子女的姓名、學校、年級、目標學校等資料。僅限子女的家長本人。", response_model=ApiResponse)
def update_student(
    student_id: int,
    body: StudentUpdate,
    user=Depends(require_role("parent")),
    conn=Depends(get_db),
):
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
