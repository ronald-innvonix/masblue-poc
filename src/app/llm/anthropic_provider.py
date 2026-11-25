"""Anthropic Claude LLM provider backed by AsyncAnthropic."""

from collections.abc import AsyncIterator
from typing import Any

import structlog
from anthropic import AnthropicError, AsyncAnthropic

from app.core.exceptions import LLMProviderError
from app.llm.base import ChatMessage, LLMProvider, ModelConfig

logger = structlog.get_logger(__name__)

_DEFAULT_ANTHROPIC_MAX_TOKENS = 4096


class AnthropicProvider(LLMProvider):
    """Async Messages API provider for Anthropic Claude models."""

    provider_name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
        client: AsyncAnthropic | None = None,
    ) -> None:
        """Initialize an AsyncAnthropic client or accept a prebuilt test client."""
        self._client = client or AsyncAnthropic(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
        )

    @staticmethod
    def _split_messages(
        messages: list[ChatMessage],
    ) -> tuple[str | None, list[dict[str, str]]]:
        """Extract system prompts for Anthropic's top-level system field."""
        system_parts: list[str] = []
        turn_messages: list[dict[str, str]] = []
        for message in messages:
            if message.role == "system":
                system_parts.append(message.content)
            else:
                turn_messages.append({"role": message.role, "content": message.content})
        system_prompt = "\n\n".join(system_parts) if system_parts else None
        return system_prompt, turn_messages

    @staticmethod
    def _build_kwargs(messages: list[ChatMessage], config: ModelConfig) -> dict[str, Any]:
        """Construct Anthropic Messages API request parameters."""
        system_prompt, turn_messages = AnthropicProvider._split_messages(messages)
        kwargs: dict[str, Any] = {
            "model": config.model,
            "messages": turn_messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens or _DEFAULT_ANTHROPIC_MAX_TOKENS,
            "timeout": config.timeout_seconds,
        }
        if system_prompt is not None:
            kwargs["system"] = system_prompt
        return kwargs

    async def generate(self, messages: list[ChatMessage], config: ModelConfig) -> str:
        """Generate a complete response via Anthropic's Messages API."""
        try:
            response = await self._client.messages.create(**self._build_kwargs(messages, config))
        except (AnthropicError, TimeoutError) as exc:
            logger.error(
                "llm_generate_failed",
                provider=self.provider_name,
                model=config.model,
                error_type=type(exc).__name__,
            )
            raise LLMProviderError() from exc

        text_parts = [
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
            and isinstance(getattr(block, "text", None), str)
        ]
        return "".join(text_parts)

    async def _stream_tokens(
        self,
        messages: list[ChatMessage],
        config: ModelConfig,
    ) -> AsyncIterator[str]:
        """Yield text chunks from Anthropic's streaming Messages API."""
        try:
            kwargs = self._build_kwargs(messages, config)
            async with self._client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    if text:
                        yield text
        except (AnthropicError, TimeoutError) as exc:
            logger.error(
                "llm_stream_failed",
                provider=self.provider_name,
                model=config.model,
                error_type=type(exc).__name__,
            )
            raise LLMProviderError() from exc

    def stream(self, messages: list[ChatMessage], config: ModelConfig) -> AsyncIterator[str]:
        """Return an async iterator of streamed text deltas."""
        return self._stream_tokens(messages, config)

    async def close(self) -> None:
        """Close the underlying AsyncAnthropic HTTP client."""
        await self._client.close()
