"""Chat endpoint request and response models."""

from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Input for a single chat turn."""

    message: str = Field(min_length=1, max_length=20_000)
    conversation_id: UUID | None = None


class ChatResponse(BaseModel):
    """Stub assistant response shape."""

    conversation_id: UUID | None
    message: str
