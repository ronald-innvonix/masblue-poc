"""Async persistence operations for messages."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message


class MessageRepository:
    """Encapsulate database reads and writes for conversation messages."""

    def __init__(self, session: AsyncSession) -> None:
        """Store the request-scoped asynchronous database session."""
        self._session = session

    async def list_for_conversation(self, conversation_id: UUID) -> list[Message]:
        """Return messages in chronological order for a conversation."""
        result = await self._session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
        )
        return list(result.scalars().all())

    async def add(self, message: Message) -> Message:
        """Add a message to the current transaction."""
        self._session.add(message)
        await self._session.flush()
        return message
