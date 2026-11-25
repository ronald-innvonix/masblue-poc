"""Async persistence operations for conversations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation


class ConversationRepository:
    """Encapsulate database reads and writes for conversations."""

    def __init__(self, session: AsyncSession) -> None:
        """Store the request-scoped asynchronous database session."""
        self._session = session

    async def get_for_user(self, conversation_id: UUID, user_id: str) -> Conversation | None:
        """Fetch a conversation only when it belongs to the supplied user."""
        result = await self._session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def add(self, conversation: Conversation) -> Conversation:
        """Add a conversation to the current transaction."""
        self._session.add(conversation)
        await self._session.flush()
        return conversation
