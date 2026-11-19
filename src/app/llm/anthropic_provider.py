"""Stub provider reserved for a future Anthropic integration."""

import asyncio
from collections.abc import AsyncIterator

from app.llm.base import LLMProvider


class AnthropicProvider(LLMProvider):
    """Provide deterministic local output without making external LLM calls."""

    async def generate(self, prompt: str) -> str:
        """Return a placeholder answer while keeping the interface asynchronous."""
        _ = prompt
        await asyncio.sleep(0)
        return "This is a stubbed AI response."

    async def _token_stream(self) -> AsyncIterator[str]:
        """Yield short fake chunks to exercise streaming clients."""
        for token in ("This ", "is ", "a ", "stubbed ", "AI ", "response."):
            await asyncio.sleep(0.05)
            yield token

    def stream(self, prompt: str) -> AsyncIterator[str]:
        """Return a fake token stream for the supplied prompt."""
        _ = prompt
        return self._token_stream()
