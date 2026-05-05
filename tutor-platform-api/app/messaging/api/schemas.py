from typing import Any

from pydantic import BaseModel, Field

from app.shared.api.validators import TrimmedStr


class MessageSend(BaseModel):
    content: TrimmedStr = Field(..., max_length=4000, description="訊息內容")


class ConversationCreate(BaseModel):
    target_user_id: int = Field(..., description="對話對象的使用者 ID")


class MessagesResponse(BaseModel):
    items: list[Any] = Field(..., description="訊息列表")
    has_more: bool = Field(..., description="是否還有更早的訊息")
    oldest_message_id: int | None = Field(None, description="本頁最舊訊息的 ID，作為下一頁 before_id 游標")
