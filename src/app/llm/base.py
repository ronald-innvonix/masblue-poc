"""Abstract asynchronous LLM provider contract."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LLMProvider(ABC):
    """Define the provider contract consumed by chat business logic."""

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """Generate a complete response for the given prompt."""

    @abstractmethod
    def stream(self, prompt: str) -> AsyncIterator[str]:
        """Return an asynchronous stream of response text chunks."""
