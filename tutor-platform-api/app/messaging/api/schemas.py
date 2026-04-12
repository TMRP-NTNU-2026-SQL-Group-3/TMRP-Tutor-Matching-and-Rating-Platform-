from pydantic import BaseModel, Field


class MessageSend(BaseModel):
    content: str = Field(..., description="訊息內容")


class ConversationCreate(BaseModel):
    target_user_id: int = Field(..., description="對話對象的使用者 ID")
