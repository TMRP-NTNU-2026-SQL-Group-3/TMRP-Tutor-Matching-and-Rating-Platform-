from pydantic import BaseModel, Field

from app.shared.api.validators import TrimmedStr


class MessageSend(BaseModel):
    content: TrimmedStr = Field(..., max_length=4000, description="訊息內容")


class ConversationCreate(BaseModel):
    target_user_id: int = Field(..., description="對話對象的使用者 ID")
