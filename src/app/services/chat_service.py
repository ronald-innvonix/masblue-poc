"""Chat use cases independent of HTTP and database details."""

from collections.abc import AsyncIterator

from app.llm.base import LLMProvider
from app.schemas.common import CurrentUser


class ChatService:
    """Coordinate chat requests through the provider abstraction."""

    def __init__(self, provider: LLMProvider) -> None:
        """Create a chat service with its injected LLM provider."""
        self._provider = provider

    async def generate_reply(self, message: str, user: CurrentUser) -> str:
        """Generate a stub reply for an authenticated user."""
        _ = user
        # TODO(phase-2): Add repository persistence, RAG, tool calling, and summarization.
        return await self._provider.generate(message)

    async def stream_reply(self, message: str, user: CurrentUser) -> AsyncIterator[str]:
        """Yield provider output incrementally for an authenticated user."""
        _ = user
        # TODO(phase-2): Add conversation persistence and usage/cost tracking.
        async for token in self._provider.stream(message):
            yield token
