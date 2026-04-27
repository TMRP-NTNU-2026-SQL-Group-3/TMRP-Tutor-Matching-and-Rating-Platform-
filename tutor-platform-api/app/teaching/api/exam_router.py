from fastapi import APIRouter, Depends, Query

from app.identity.api.dependencies import get_current_user, get_db, is_admin
from app.middleware.rate_limit import check_and_record_bucket
from app.shared.api.schemas import ApiResponse
from app.shared.domain.exceptions import (
    DomainException,
    NotFoundError,
    PermissionDeniedError,
    TooManyRequestsError,
)
from app.teaching.api.schemas import ExamCreate, ExamUpdate
from app.teaching.infrastructure.postgres_exam_repo import PostgresExamRepository

router = APIRouter(prefix="/api/exams", tags=["exams"])

# B6: Per-student+author bucket. Even with the global /api/exams path
# limit, a single student's record could be flooded by one user making
# many small creates; this caps how fast any one user can add exams for
# any one student.
_EXAM_CREATE_LIMIT = 20
_EXAM_CREATE_WINDOW = 60


@router.post("", status_code=201, summary="新增考試紀錄", response_model=ApiResponse)
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
    is_tutor = role == "tutor" and bool(
        repo.get_active_match_for_tutor_subject(body.student_id, user_id, body.subject_id)
    )
    if not is_parent and not is_tutor:
        raise PermissionDeniedError("無權為此學生新增考試紀錄")
    bucket = f"exam:create|student={body.student_id}|user={user_id}"
    if not check_and_record_bucket(bucket, _EXAM_CREATE_LIMIT, _EXAM_CREATE_WINDOW):
        raise TooManyRequestsError("此學生的考試紀錄新增頻率過高，請稍後再試")
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
    # S-H6: use role to gate the tutor path, not any-subject match presence.
    # list_by_student_for_tutor enforces subject-level access via the
    # JOIN on matches.subject_id — a tutor only sees exams for subjects they
    # are actively matched on, regardless of other matches for this student.
    is_tutor_role = user["role"] == "tutor"
    has_match = is_tutor_role and bool(repo.get_active_match_for_tutor(student_id, user_id))
    if not is_parent and not has_match and not is_admin(user):
        raise PermissionDeniedError("無權查看此學生的考試紀錄")
    if has_match and not is_parent and not is_admin(user):
        exams = repo.list_by_student_for_tutor(student_id, user_id)
    else:
        exams = repo.list_by_student(student_id, parent_only=is_parent and not is_admin(user))
    return ApiResponse(success=True, data=exams)


@router.delete("/{exam_id}", summary="刪除考試紀錄", response_model=ApiResponse)
def delete_exam(exam_id: int, user=Depends(get_current_user), conn=Depends(get_db)):
    repo = PostgresExamRepository(conn)
    user_id = int(user["sub"])
    exam = repo.get_by_id(exam_id)
    if not exam:
        raise NotFoundError("找不到此考試紀錄")
    if exam["added_by_user_id"] != user_id:
        raise PermissionDeniedError("只有原新增者可以刪除考試紀錄")
    repo.delete(exam_id)
    return ApiResponse(success=True, message="考試紀錄已刪除")


@router.put("/{exam_id}", summary="修改考試紀錄", response_model=ApiResponse)
def update_exam(exam_id: int, body: ExamUpdate, user=Depends(get_current_user), conn=Depends(get_db)):
    repo = PostgresExamRepository(conn)
    user_id = int(user["sub"])
    exam = repo.get_by_id(exam_id)
    if not exam:
        raise NotFoundError("找不到此考試紀錄")
    if exam["added_by_user_id"] != user_id:
        raise PermissionDeniedError("只有原新增者可以修改考試紀錄")
    updates = {
        k: (bool(v) if k == "visible_to_parent" else v)
        for k, v in body.model_dump(exclude_unset=True).items()
        if v is not None or k == "visible_to_parent"
    }
    if not updates:
        return ApiResponse(success=True, data={}, message="無需更新的欄位")
    repo.update(exam_id, updates)
    return ApiResponse(success=True, data={"exam_id": exam_id}, message="考試紀錄已更新")
