"""Chat use cases independent of HTTP and database details."""

from collections.abc import AsyncIterator

from app.llm.base import ChatMessage, LLMProvider, ModelConfig
from app.schemas.common import CurrentUser

DEFAULT_CHAT_SYSTEM_PROMPT = (
    "You are the Masblue AI Assistant. Provide clear, concise, and helpful responses."
)


class ChatService:
    """Coordinate chat requests through the provider abstraction."""

    def __init__(
        self,
        provider: LLMProvider,
        model_config: ModelConfig,
        system_prompt: str | None = DEFAULT_CHAT_SYSTEM_PROMPT,
    ) -> None:
        """Create a chat service with its injected LLM provider and model config."""
        self._provider = provider
        self._model_config = model_config
        self._system_prompt = system_prompt

    def _build_messages(self, message: str) -> list[ChatMessage]:
        """Assemble provider-agnostic messages for a single chat turn."""
        messages: list[ChatMessage] = []
        if self._system_prompt:
            messages.append(ChatMessage(role="system", content=self._system_prompt))
        messages.append(ChatMessage(role="user", content=message))
        return messages

    async def generate_reply(self, message: str, user: CurrentUser) -> str:
        """Generate a complete assistant reply for an authenticated user."""
        _ = user
        # TODO(phase-2): Add repository persistence, RAG, tool calling, and summarization.
        return await self._provider.generate(self._build_messages(message), self._model_config)

    async def stream_reply(self, message: str, user: CurrentUser) -> AsyncIterator[str]:
        """Yield provider output incrementally for an authenticated user."""
        _ = user
        # TODO(phase-2): Add conversation persistence and usage/cost tracking.
        async for token in self._provider.stream(
            self._build_messages(message),
            self._model_config,
        ):
            yield token
