from fastapi import APIRouter, Depends

from app.identity.api.dependencies import get_current_user, is_admin
from app.middleware.rate_limit import check_and_record_bucket
from app.shared.api.schemas import ApiResponse
from app.shared.domain.exceptions import TooManyRequestsError
from app.teaching.api.dependencies import get_exam_service
from app.teaching.api.schemas import ExamCreate, ExamCreateBody, ExamUpdate
from app.teaching.application.exam_service import ExamAppService

# Spec §7.7: POST/GET /api/students/{student_id}/exams
student_exams_router = APIRouter(prefix="/api/students", tags=["exams"])
# Remaining exam-specific routes stay under /api/exams
router = APIRouter(prefix="/api/exams", tags=["exams"])

# B6: Per-student+author bucket. Even with the global /api/exams path
# limit, a single student's record could be flooded by one user making
# many small creates; this caps how fast any one user can add exams for
# any one student.
_EXAM_CREATE_LIMIT = 20
_EXAM_CREATE_WINDOW = 60


@student_exams_router.post("/{student_id}/exams", status_code=201, summary="新增考試紀錄", response_model=ApiResponse)
def create_exam(
    student_id: int,
    body: ExamCreateBody,
    user=Depends(get_current_user),
    service: ExamAppService = Depends(get_exam_service),
):
    user_id = int(user["sub"])
    bucket = f"exam:create|student={student_id}|user={user_id}"
    if not check_and_record_bucket(bucket, _EXAM_CREATE_LIMIT, _EXAM_CREATE_WINDOW):
        raise TooManyRequestsError("此學生的考試紀錄新增頻率過高，請稍後再試")
    full_body = ExamCreate(student_id=student_id, **body.model_dump())
    exam_id = service.create_exam(user_id=user_id, role=user["role"], body=full_body)
    return ApiResponse(success=True, data={"exam_id": exam_id}, message="考試紀錄已新增")


@student_exams_router.get("/{student_id}/exams", summary="列出考試紀錄", response_model=ApiResponse)
def list_exams(
    student_id: int,
    user=Depends(get_current_user),
    service: ExamAppService = Depends(get_exam_service),
):
    exams = service.list_exams(
        user_id=int(user["sub"]),
        role=user["role"],
        student_id=student_id,
        is_admin=is_admin(user),
    )
    return ApiResponse(success=True, data=exams)


@router.delete("/{exam_id}", summary="刪除考試紀錄", response_model=ApiResponse)
def delete_exam(
    exam_id: int,
    user=Depends(get_current_user),
    service: ExamAppService = Depends(get_exam_service),
):
    service.delete_exam(exam_id=exam_id, user_id=int(user["sub"]))
    return ApiResponse(success=True, message="考試紀錄已刪除")


@router.put("/{exam_id}", summary="修改考試紀錄", response_model=ApiResponse)
def update_exam(
    exam_id: int,
    body: ExamUpdate,
    user=Depends(get_current_user),
    service: ExamAppService = Depends(get_exam_service),
):
    updates = {
        k: (bool(v) if k == "visible_to_parent" else v)
        for k, v in body.model_dump(exclude_unset=True).items()
        if v is not None or k == "visible_to_parent"
    }
    if not updates:
        return ApiResponse(success=True, data={}, message="無需更新的欄位")
    service.update_exam(exam_id=exam_id, user_id=int(user["sub"]), updates=updates)
    return ApiResponse(success=True, data={"exam_id": exam_id}, message="考試紀錄已更新")
