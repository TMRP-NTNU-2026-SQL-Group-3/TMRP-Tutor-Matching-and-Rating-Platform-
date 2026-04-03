from pydantic import BaseModel


class MessageSend(BaseModel):
    content: str


class ConversationCreate(BaseModel):
    target_user_id: int
