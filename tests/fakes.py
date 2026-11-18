from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.llm.base import EmbeddingProvider, LLMProvider, LLMResponse


class FakeLLMProvider(LLMProvider):
    def __init__(self, response_text: str = "Answer from supplied context.") -> None:
        self.response_text = response_text
        self.calls = 0
        self.last_messages: list[dict[str, str]] = []

    async def complete(
        self, system: str, messages: list[dict[str, str]], max_tokens: int, temperature: float
    ) -> LLMResponse:
        self.calls += 1
        self.last_messages = messages
        return LLMResponse(self.response_text, "fake-llm", 12, 8, 1)

    async def stream(
        self, system: str, messages: list[dict[str, str]], max_tokens: int, temperature: float
    ) -> AsyncIterator[str]:
        self.calls += 1
        self.last_messages = messages
        yield self.response_text


@dataclass
class FakeEmbeddingProvider(EmbeddingProvider):
    dimensions: int = 384

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, *([0.0] * (self.dimensions - 1))] for _ in texts]
