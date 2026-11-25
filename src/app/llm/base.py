"""Abstract asynchronous LLM provider contract and shared message/config types."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

MessageRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """Provider-agnostic chat turn passed to an LLM backend."""

    role: MessageRole
    content: str


@dataclass(frozen=True, slots=True)
class ModelConfig:
    """Execution parameters controlling model selection and sampling."""

    model: str
    temperature: float = 0.0
    max_tokens: int | None = None
    timeout_seconds: float = 30.0


class LLMProvider(ABC):
    """Define the provider contract consumed by chat and intent services."""

    @abstractmethod
    async def generate(self, messages: list[ChatMessage], config: ModelConfig) -> str:
        """Generate a complete response for the given conversation messages."""

    @abstractmethod
    def stream(self, messages: list[ChatMessage], config: ModelConfig) -> AsyncIterator[str]:
        """Return an asynchronous stream of response text chunks."""

    @abstractmethod
    async def close(self) -> None:
        """Release underlying HTTP/SDK client resources when applicable."""
