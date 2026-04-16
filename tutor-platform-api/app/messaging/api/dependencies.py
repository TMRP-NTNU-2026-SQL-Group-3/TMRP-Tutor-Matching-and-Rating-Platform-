"""FastAPI dependencies for the messaging bounded context."""

from fastapi import Depends

from app.identity.api.dependencies import get_db
from app.messaging.application.message_service import MessageAppService
from app.messaging.infrastructure.postgres_conversation_repo import PostgresConversationRepository
from app.messaging.infrastructure.postgres_message_repo import PostgresMessageRepository


def get_message_service(conn=Depends(get_db)) -> MessageAppService:
    return MessageAppService(
        repo=PostgresMessageRepository(conn),
        conv_repo=PostgresConversationRepository(conn),
        conn=conn,
    )
