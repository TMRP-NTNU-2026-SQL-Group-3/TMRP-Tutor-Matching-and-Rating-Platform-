from fastapi import APIRouter, Depends, Query

from app.identity.api.dependencies import require_role
from app.messaging.api.dependencies import get_message_service
from app.messaging.api.schemas import ConversationCreate, MessageSend
from app.messaging.application.message_service import MessageAppService
from app.middleware.rate_limit import check_and_record_bucket
from app.shared.api.schemas import ApiResponse
from app.shared.domain.exceptions import TooManyRequestsError

router = APIRouter(prefix="/api/messages", tags=["messages"])

# I-04: per-conversation-per-user bucket so one user cannot flood a peer's
# inbox. The global /api/messages/* path bucket would only catch bursts
# across all conversations at once; this catches harassment targeting a
# single counterparty.
_MESSAGE_SEND_LIMIT = 30
_MESSAGE_SEND_WINDOW = 60
# SEC-04: global per-user ceiling prevents N-conversation multiplication.
# A user with N open conversations could otherwise send 30*N msgs/min.
_MESSAGE_GLOBAL_LIMIT = 100
_MESSAGE_GLOBAL_WINDOW = 3600  # 1 hour


@router.post("/conversations", status_code=201, summary="建立對話", response_model=ApiResponse)
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


@router.post("/conversations/{conversation_id}", status_code=201, summary="傳送訊息", response_model=ApiResponse)
def send_message(
    conversation_id: int,
    body: MessageSend,
    user=Depends(require_role("parent", "tutor")),
    service: MessageAppService = Depends(get_message_service),
):
    # SEC-9: extract and validate content first so rate-limit quota is only
    # debited for requests that pass schema validation. FastAPI validates the
    # MessageSend Pydantic model (non-empty TrimmedStr, ≤4000 chars) before
    # this handler runs, so `content` is guaranteed non-empty here.
    content = body.content
    user_id = int(user["sub"])
    bucket = f"message:send|conv={conversation_id}|user={user_id}"
    if not check_and_record_bucket(bucket, _MESSAGE_SEND_LIMIT, _MESSAGE_SEND_WINDOW):
        raise TooManyRequestsError("傳送訊息過於頻繁，請稍後再試")
    global_bucket = f"message:send|user={user_id}"
    if not check_and_record_bucket(global_bucket, _MESSAGE_GLOBAL_LIMIT, _MESSAGE_GLOBAL_WINDOW):
        raise TooManyRequestsError("傳送訊息過於頻繁，請稍後再試")
    msg_id = service.send_message(
        conversation_id=conversation_id,
        user_id=user_id,
        content=content,
    )
    return ApiResponse(success=True, data={"message_id": msg_id}, message="訊息已送出")
