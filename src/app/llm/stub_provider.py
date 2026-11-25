"""Deterministic local stub LLM provider for offline development and tests."""

import asyncio
from collections.abc import AsyncIterator

from app.llm.base import ChatMessage, LLMProvider, ModelConfig


class StubProvider(LLMProvider):
    """Provide deterministic local output without making external LLM calls."""

    async def generate(self, messages: list[ChatMessage], config: ModelConfig) -> str:
        """Return a placeholder answer while keeping the interface asynchronous."""
        _ = (messages, config)
        await asyncio.sleep(0)
        return "This is a stubbed AI response."

    async def _token_stream(self) -> AsyncIterator[str]:
        """Yield short fake chunks to exercise streaming clients."""
        for token in ("This ", "is ", "a ", "stubbed ", "AI ", "response."):
            await asyncio.sleep(0.05)
            yield token

    def stream(self, messages: list[ChatMessage], config: ModelConfig) -> AsyncIterator[str]:
        """Return a fake token stream for the supplied messages."""
        _ = (messages, config)
        return self._token_stream()

    async def close(self) -> None:
        """No-op cleanup for the local stub provider."""
        return None
