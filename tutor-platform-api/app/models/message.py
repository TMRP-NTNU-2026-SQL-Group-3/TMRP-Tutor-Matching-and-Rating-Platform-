from pydantic import BaseModel, Field


class MessageSend(BaseModel):
    content: str = Field(..., description="訊息內容", examples=["您好，想請問週三下午有空嗎？"])


class ConversationCreate(BaseModel):
    target_user_id: int = Field(..., description="對話對象的使用者 ID", examples=[2])
