from fastapi import APIRouter, Depends, Query

from app.identity.api.dependencies import get_current_user, get_db, is_admin
from app.shared.api.schemas import ApiResponse
from app.shared.domain.exceptions import DomainException, NotFoundError, PermissionDeniedError
from app.teaching.api.schemas import ExamCreate, ExamUpdate
from app.teaching.infrastructure.postgres_exam_repo import PostgresExamRepository

router = APIRouter(prefix="/api/exams", tags=["exams"])


@router.post("", summary="新增考試紀錄", response_model=ApiResponse)
def create_exam(body: ExamCreate, user=Depends(get_current_user), conn=Depends(get_db)):
    role = user["role"]
    if role not in ("parent", "tutor"):
        raise DomainException("僅家長或老師可新增考試紀錄")
    repo = PostgresExamRepository(conn)
    user_id = int(user["sub"])
    student = repo.get_student(body.student_id)
    if not student:
        raise NotFoundError("找不到此學生")
    is_parent = role == "parent" and student["parent_user_id"] == user_id
    is_tutor = role == "tutor" and bool(repo.get_active_match_for_tutor(body.student_id, user_id))
    if not is_parent and not is_tutor:
        raise PermissionDeniedError("無權為此學生新增考試紀錄")
    exam_id = repo.create(
        student_id=body.student_id, subject_id=body.subject_id,
        added_by_user_id=user_id, exam_date=body.exam_date,
        exam_type=body.exam_type, score=body.score,
        visible_to_parent=body.visible_to_parent,
    )
    return ApiResponse(success=True, data={"exam_id": exam_id}, message="考試紀錄已新增")


@router.get("", summary="列出考試紀錄", response_model=ApiResponse)
def list_exams(student_id: int = Query(...), user=Depends(get_current_user), conn=Depends(get_db)):
    repo = PostgresExamRepository(conn)
    user_id = int(user["sub"])
    student = repo.get_student(student_id)
    if not student:
        raise NotFoundError("找不到此學生")
    is_parent = student["parent_user_id"] == user_id
    is_tutor = bool(repo.get_active_match_for_tutor(student_id, user_id))
    if not is_parent and not is_tutor and not is_admin(user):
        raise PermissionDeniedError("無權查看此學生的考試紀錄")
    exams = repo.list_by_student(student_id, parent_only=is_parent and not is_tutor)
    return ApiResponse(success=True, data=exams)


@router.put("/{exam_id}", summary="修改考試紀錄", response_model=ApiResponse)
def update_exam(exam_id: int, body: ExamUpdate, user=Depends(get_current_user), conn=Depends(get_db)):
    repo = PostgresExamRepository(conn)
    user_id = int(user["sub"])
    exam = repo.get_by_id(exam_id)
    if not exam:
        raise NotFoundError("找不到此考試紀錄")
    if exam["added_by_user_id"] != user_id:
        raise PermissionDeniedError("只有原新增者可以修改考試紀錄")
    updates = {}
    for k, v in body.model_dump(exclude_unset=True).items():
        if k == "visible_to_parent":
            if v is not None:
                updates[k] = bool(v)
        else:
            updates[k] = v
    if not updates:
        return ApiResponse(success=True, data={}, message="無需更新的欄位")
    repo.update(exam_id, updates)
    return ApiResponse(success=True, data={"exam_id": exam_id}, message="考試紀錄已更新")
