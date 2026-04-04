from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_db, is_admin, require_role
from app.exceptions import AppException, ConflictException, ForbiddenException, NotFoundException
from app.models.common import ApiResponse
from app.models.match import MatchCreate, MatchStatusUpdate
from app.repositories.match_repo import MatchRepository
from app.repositories.student_repo import StudentRepository
from app.repositories.tutor_repo import TutorRepository

router = APIRouter(prefix="/api/matches", tags=["matches"])

# 狀態機定義：(current_status, action) -> (new_status, who_can_do_it)
# who_can_do_it: "parent", "tutor", "either", "other_party"
TRANSITIONS = {
    ("pending", "cancel"): ("cancelled", "parent"),
    ("pending", "reject"): ("rejected", "tutor"),
    ("pending", "accept"): (None, "tutor"),  # special: trial or active
    ("trial", "confirm_trial"): ("active", "either"),
    ("trial", "reject_trial"): ("rejected", "either"),
    ("active", "pause"): ("paused", "either"),
    ("active", "terminate"): ("terminating", "either"),
    ("paused", "resume"): ("active", "either"),
    ("paused", "terminate"): ("terminating", "either"),
    ("terminating", "agree_terminate"): ("ended", "other_party"),
    ("terminating", "disagree_terminate"): (None, "other_party"),  # special: revert
}

STATUS_LABELS = {
    "pending": "等待中",
    "trial": "試教中",
    "active": "進行中",
    "paused": "已暫停",
    "cancelled": "已取消",
    "rejected": "已拒絕",
    "terminating": "等待終止確認",
    "ended": "已結束",
}


@router.post("", summary="建立配對邀請", description="家長為指定學生向家教發送配對邀請，需包含科目、時薪、堂數等合約條件。系統會驗證學生歸屬、老師存在、科目對應、重複配對及容量上限。", response_model=ApiResponse)
def create_match(
    body: MatchCreate,
    user=Depends(require_role("parent")),
    conn=Depends(get_db),
):
    user_id = int(user["sub"])
    student_repo = StudentRepository(conn)
    tutor_repo = TutorRepository(conn)
    match_repo = MatchRepository(conn)

    # 驗證子女屬於此家長
    student = student_repo.find_by_id(body.student_id)
    if not student or student["parent_user_id"] != user_id:
        raise ForbiddenException("此子女不屬於您")

    # 驗證老師存在
    tutor = tutor_repo.find_by_id(body.tutor_id)
    if not tutor:
        raise NotFoundException("找不到此老師")

    # 驗證老師有教此科目
    subjects = tutor_repo.get_subjects(body.tutor_id)
    subject_ids = [s["subject_id"] for s in subjects]
    if body.subject_id not in subject_ids:
        raise AppException("此老師未提供此科目的教學")

    # 檢查重複
    if match_repo.check_duplicate_active(body.tutor_id, body.student_id, body.subject_id):
        raise ConflictException("已存在進行中的配對")

    # 檢查老師容量
    active_count = tutor_repo.get_active_student_count(body.tutor_id)
    max_students = tutor.get("max_students") or 5
    if active_count >= max_students:
        raise AppException("此老師已達收生上限")

    match_id = match_repo.create(
        tutor_id=body.tutor_id,
        student_id=body.student_id,
        subject_id=body.subject_id,
        hourly_rate=body.hourly_rate,
        sessions_per_week=body.sessions_per_week,
        want_trial=body.want_trial,
        invite_message=body.invite_message,
    )
    return ApiResponse(success=True, data={"match_id": match_id}, message="媒合邀請已送出")


@router.get("", summary="列出我的配對", description="列出目前登入使用者的所有配對。家長看到子女的配對，家教看到自己的配對。", response_model=ApiResponse)
def list_matches(user=Depends(get_current_user), conn=Depends(get_db)):
    user_id = int(user["sub"])
    role = user["role"]
    repo = MatchRepository(conn)

    if role == "tutor":
        matches = repo.find_by_tutor_user_id(user_id)
    else:
        matches = repo.find_by_parent_user_id(user_id)

    for m in matches:
        m["status_label"] = STATUS_LABELS.get(m["status"], m["status"])

    return ApiResponse(success=True, data=matches)


@router.get("/{match_id}", summary="取得配對詳情", description="取得指定配對的完整資訊，包含科目、學生、老師名稱。僅限配對參與者或管理員。", response_model=ApiResponse)
def get_match_detail(
    match_id: int,
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    repo = MatchRepository(conn)
    match = repo.find_by_id(match_id)
    if not match:
        raise NotFoundException("找不到此配對")

    user_id = int(user["sub"])
    is_parent = match["parent_user_id"] == user_id
    is_tutor = match["tutor_user_id"] == user_id

    if not is_parent and not is_tutor and not is_admin(user):
        raise ForbiddenException("無權查看此配對")

    match["status_label"] = STATUS_LABELS.get(match["status"], match["status"])
    match["is_parent"] = is_parent
    match["is_tutor"] = is_tutor

    return ApiResponse(success=True, data=match)


@router.patch("/{match_id}/status", summary="更新配對狀態", description="依照狀態機規則變更配對狀態。支援的操作包含：accept、reject、cancel、confirm_trial、reject_trial、pause、resume、terminate、agree_terminate、disagree_terminate。每個操作有對應的角色權限限制。", response_model=ApiResponse)
def update_match_status(
    match_id: int,
    body: MatchStatusUpdate,
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    repo = MatchRepository(conn)
    match = repo.find_by_id(match_id)
    if not match:
        raise NotFoundException("找不到此配對")

    user_id = int(user["sub"])
    is_parent = match["parent_user_id"] == user_id
    is_tutor = match["tutor_user_id"] == user_id

    if not is_parent and not is_tutor:
        raise ForbiddenException("無權操作此配對")

    current_status = match["status"]
    action = body.action

    # 查找轉換規則
    transition = TRANSITIONS.get((current_status, action))
    if not transition:
        raise AppException(f"無法在「{STATUS_LABELS.get(current_status, current_status)}」狀態執行「{action}」操作")

    new_status, who = transition

    # 權限檢查
    if who == "parent" and not is_parent:
        raise ForbiddenException("只有家長可以執行此操作")
    elif who == "tutor" and not is_tutor:
        raise ForbiddenException("只有老師可以執行此操作")
    elif who == "other_party":
        # 必須是發起終止的對方
        terminated_by = match.get("terminated_by")
        if terminated_by == user_id:
            raise ForbiddenException("需要由對方確認此操作")

    # 處理特殊轉換
    if action == "accept":
        new_status = "trial" if match.get("want_trial") else "active"
        repo.update_status(match_id, new_status)

    elif action == "terminate":
        if not body.reason:
            raise AppException("終止配對需要提供原因")
        repo.set_terminating(match_id, user_id, body.reason, current_status)

    elif action == "disagree_terminate":
        # 從 termination_reason 解析出 previous_status
        reason_raw = match.get("termination_reason") or "active"
        previous_status = reason_raw.split("|")[0] if "|" in reason_raw else "active"
        if previous_status not in ("active", "paused"):
            previous_status = "active"
        repo.clear_termination(match_id, previous_status)
        new_status = previous_status

    else:
        repo.update_status(match_id, new_status)

    return ApiResponse(
        success=True,
        data={"match_id": match_id, "new_status": new_status},
        message=f"配對狀態已更新為「{STATUS_LABELS.get(new_status, new_status)}」",
    )
