from fastapi import APIRouter, Depends

from app.identity.api.dependencies import get_db, require_role
from app.messaging.api.schemas import ConversationCreate, MessageSend
from app.messaging.infrastructure.postgres_message_repo import PostgresMessageRepository
from app.shared.api.schemas import ApiResponse
from app.shared.domain.exceptions import DomainException, NotFoundError, PermissionDeniedError
from app.shared.infrastructure.base_repository import BaseRepository

router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.post("/conversations", summary="建立對話", response_model=ApiResponse)
def create_conversation(body: ConversationCreate, user=Depends(require_role("parent", "tutor")), conn=Depends(get_db)):
    user_id = int(user["sub"])
    if user_id == body.target_user_id:
        raise DomainException("不能與自己建立對話")
    base = BaseRepository(conn)
    target = base.fetch_one("SELECT user_id FROM users WHERE user_id = %s", (body.target_user_id,))
    if not target:
        raise NotFoundError("找不到該使用者")
    repo = PostgresMessageRepository(conn)
    conv_id = repo.get_or_create_conversation(user_id, body.target_user_id)
    return ApiResponse(success=True, data={"conversation_id": conv_id})


@router.get("/conversations", summary="列出對話", response_model=ApiResponse)
def list_conversations(user=Depends(require_role("parent", "tutor")), conn=Depends(get_db)):
    repo = PostgresMessageRepository(conn)
    conversations = repo.find_conversations_for_user(int(user["sub"]))
    return ApiResponse(success=True, data=conversations)


@router.get("/conversations/{conversation_id}", summary="取得對話訊息", response_model=ApiResponse)
def get_messages(conversation_id: int, user=Depends(require_role("parent", "tutor")), conn=Depends(get_db)):
    user_id = int(user["sub"])
    repo = PostgresMessageRepository(conn)
    if not repo.user_is_participant(conversation_id, user_id):
        raise PermissionDeniedError("無權查看此對話")
    messages = repo.get_messages(conversation_id)
    return ApiResponse(success=True, data=messages)


@router.post("/conversations/{conversation_id}", summary="傳送訊息", response_model=ApiResponse)
def send_message(conversation_id: int, body: MessageSend, user=Depends(require_role("parent", "tutor")), conn=Depends(get_db)):
    user_id = int(user["sub"])
    if not body.content or not body.content.strip():
        raise DomainException("訊息內容不可為空")
    repo = PostgresMessageRepository(conn)
    if not repo.user_is_participant(conversation_id, user_id):
        raise PermissionDeniedError("無權在此對話中發送訊息")
    msg_id = repo.send_message(conversation_id, user_id, body.content.strip())
    return ApiResponse(success=True, data={"message_id": msg_id}, message="訊息已送出")
