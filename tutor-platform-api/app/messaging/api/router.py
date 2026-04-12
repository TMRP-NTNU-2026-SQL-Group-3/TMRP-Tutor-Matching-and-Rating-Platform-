from fastapi import APIRouter, Depends, Query

from app.identity.api.dependencies import require_role
from app.messaging.api.dependencies import get_message_service
from app.messaging.api.schemas import ConversationCreate, MessageSend
from app.messaging.application.message_service import MessageAppService
from app.shared.api.schemas import ApiResponse

router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.post("/conversations", summary="建立對話", response_model=ApiResponse)
def create_conversation(
    body: ConversationCreate,
    user=Depends(require_role("parent", "tutor")),
    service: MessageAppService = Depends(get_message_service),
):
    conv_id = service.create_conversation(
        user_id=int(user["sub"]), target_user_id=body.target_user_id,
    )
    return ApiResponse(success=True, data={"conversation_id": conv_id})


@router.get("/conversations", summary="列出對話", response_model=ApiResponse)
def list_conversations(
    user=Depends(require_role("parent", "tutor")),
    service: MessageAppService = Depends(get_message_service),
):
    conversations = service.list_conversations(user_id=int(user["sub"]))
    return ApiResponse(success=True, data=conversations)


@router.get("/conversations/{conversation_id}", summary="取得對話訊息", response_model=ApiResponse)
def get_messages(
    conversation_id: int,
    limit: int = Query(100, ge=1, le=500),
    before_id: int | None = Query(None, ge=1),
    user=Depends(require_role("parent", "tutor")),
    service: MessageAppService = Depends(get_message_service),
):
    messages = service.get_messages(
        conversation_id=conversation_id,
        user_id=int(user["sub"]),
        limit=limit,
        before_id=before_id,
    )
    return ApiResponse(success=True, data=messages)


@router.post("/conversations/{conversation_id}", summary="傳送訊息", response_model=ApiResponse)
def send_message(
    conversation_id: int,
    body: MessageSend,
    user=Depends(require_role("parent", "tutor")),
    service: MessageAppService = Depends(get_message_service),
):
    msg_id = service.send_message(
        conversation_id=conversation_id,
        user_id=int(user["sub"]),
        content=body.content,
    )
    return ApiResponse(success=True, data={"message_id": msg_id}, message="訊息已送出")
