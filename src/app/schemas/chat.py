"""Chat endpoint request and response models."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    """Input for a single chat turn."""

    message: str = Field(min_length=1, max_length=20_000)
    conversation_id: UUID | None = None


class ChatResponse(BaseModel):
    """Stub assistant response shape."""

    conversation_id: UUID | None
    message: str


class MessageItem(BaseModel):
    """A persisted message returned by the conversation history API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    content: str
    citations: list[dict[str, Any]] | None
    intent: str | None
    created_at: datetime


class ConversationMessagesResponse(BaseModel):
    """Paginated conversation history in chronological order."""

    conversation_id: UUID
    page: int
    page_size: int
    total: int
    messages: list[MessageItem]
