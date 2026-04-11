from fastapi import APIRouter, Depends

from app.dependencies import get_db, require_role
from app.exceptions import AppException, ForbiddenException, NotFoundException
from app.models.common import ApiResponse
from app.models.message import ConversationCreate, MessageSend
from app.repositories.base import BaseRepository
from app.repositories.message_repo import MessageRepository

router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.post("/conversations", summary="建立對話", description="與指定使用者建立新對話，若已存在則回傳既有的 conversation_id。不可與自己建立對話。", response_model=ApiResponse)
def create_conversation(
    body: ConversationCreate,
    user=Depends(require_role("parent", "tutor")),
    conn=Depends(get_db),
):
    user_id = int(user["sub"])
    if user_id == body.target_user_id:
        raise AppException("不能與自己建立對話")

    # 驗證對方存在
    base = BaseRepository(conn)
    target = base.fetch_one("SELECT user_id FROM users WHERE user_id = %s", (body.target_user_id,))
    if not target:
        raise NotFoundException("找不到該使用者")

    repo = MessageRepository(conn)
    conv_id = repo.get_or_create_conversation(user_id, body.target_user_id)
    return ApiResponse(success=True, data={"conversation_id": conv_id})


@router.get("/conversations", summary="列出對話", description="列出目前登入使用者的所有對話，依最後訊息時間排序。", response_model=ApiResponse)
def list_conversations(user=Depends(require_role("parent", "tutor")), conn=Depends(get_db)):
    repo = MessageRepository(conn)
    conversations = repo.find_conversations_for_user(int(user["sub"]))
    return ApiResponse(success=True, data=conversations)


@router.get("/conversations/{conversation_id}", summary="取得對話訊息", description="取得指定對話的所有訊息，依送出時間排序。僅限對話參與者。", response_model=ApiResponse)
def get_messages(
    conversation_id: int,
    user=Depends(require_role("parent", "tutor")),
    conn=Depends(get_db),
):
    user_id = int(user["sub"])
    repo = MessageRepository(conn)

    if not repo.user_is_participant(conversation_id, user_id):
        raise ForbiddenException("無權查看此對話")

    messages = repo.get_messages(conversation_id)
    return ApiResponse(success=True, data=messages)


@router.post("/conversations/{conversation_id}", summary="傳送訊息", description="在指定對話中傳送一則訊息，內容不可為空。僅限對話參與者。", response_model=ApiResponse)
def send_message(
    conversation_id: int,
    body: MessageSend,
    user=Depends(require_role("parent", "tutor")),
    conn=Depends(get_db),
):
    user_id = int(user["sub"])
    if not body.content or not body.content.strip():
        raise AppException("訊息內容不可為空")

    repo = MessageRepository(conn)

    if not repo.user_is_participant(conversation_id, user_id):
        raise ForbiddenException("無權在此對話中發送訊息")

    msg_id = repo.send_message(conversation_id, user_id, body.content.strip())
    return ApiResponse(success=True, data={"message_id": msg_id}, message="訊息已送出")
