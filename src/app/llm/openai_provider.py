"""OpenAI-compatible LLM provider covering OpenAI, Grok (xAI), Gemini, and local servers."""

from collections.abc import AsyncIterator
from typing import Any

import structlog
from openai import AsyncOpenAI, OpenAIError

from app.core.exceptions import LLMProviderError
from app.llm.base import ChatMessage, LLMProvider, ModelConfig

logger = structlog.get_logger(__name__)

GROK_DEFAULT_BASE_URL = "https://api.x.ai/v1"
GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class OpenAICompatibleProvider(LLMProvider):
    """Async chat completions provider backed by the OpenAI SDK."""

    provider_name = "openai_compatible"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
        client: AsyncOpenAI | None = None,
    ) -> None:
        """Initialize an AsyncOpenAI client or accept a prebuilt test client."""
        self._client = client or AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
        )

    @staticmethod
    def _format_messages(messages: list[ChatMessage]) -> list[dict[str, str]]:
        """Serialize provider-agnostic messages into OpenAI chat dicts."""
        return [{"role": message.role, "content": message.content} for message in messages]

    @staticmethod
    def _build_kwargs(
        messages: list[ChatMessage],
        config: ModelConfig,
        *,
        stream: bool,
    ) -> dict[str, Any]:
        """Build completion arguments while omitting unset optional limits."""
        kwargs: dict[str, Any] = {
            "model": config.model,
            "messages": OpenAICompatibleProvider._format_messages(messages),
            "temperature": config.temperature,
            "stream": stream,
            "timeout": config.timeout_seconds,
        }
        if config.max_tokens is not None:
            kwargs["max_tokens"] = config.max_tokens
        return kwargs

    async def generate(self, messages: list[ChatMessage], config: ModelConfig) -> str:
        """Generate a complete response via the OpenAI chat completions endpoint."""
        try:
            response = await self._client.chat.completions.create(
                **self._build_kwargs(messages, config, stream=False),
            )
        except (OpenAIError, TimeoutError) as exc:
            logger.error(
                "llm_generate_failed",
                provider=self.provider_name,
                model=config.model,
                error_type=type(exc).__name__,
            )
            raise LLMProviderError() from exc

        choices = getattr(response, "choices", None) or []
        if not choices:
            logger.error(
                "llm_empty_choices",
                provider=self.provider_name,
                model=config.model,
            )
            raise LLMProviderError("Upstream LLM returned an empty response")
        content: str | None = choices[0].message.content
        if content is None:
            return ""
        return content

    async def _stream_tokens(
        self,
        messages: list[ChatMessage],
        config: ModelConfig,
    ) -> AsyncIterator[str]:
        """Yield non-empty delta text chunks from a streaming completion response."""
        try:
            stream = await self._client.chat.completions.create(
                **self._build_kwargs(messages, config, stream=True),
            )
            async for chunk in stream:
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                delta = choices[0].delta
                token: str | None = getattr(delta, "content", None)
                if token:
                    yield token
        except (OpenAIError, TimeoutError) as exc:
            logger.error(
                "llm_stream_failed",
                provider=self.provider_name,
                model=config.model,
                error_type=type(exc).__name__,
            )
            raise LLMProviderError() from exc

    def stream(self, messages: list[ChatMessage], config: ModelConfig) -> AsyncIterator[str]:
        """Return an async iterator of text deltas from the completion stream."""
        return self._stream_tokens(messages, config)

    async def close(self) -> None:
        """Close the underlying AsyncOpenAI HTTP client."""
        await self._client.close()


class OpenAIProvider(OpenAICompatibleProvider):
    """Official OpenAI provider."""

    provider_name = "openai"


class GrokProvider(OpenAICompatibleProvider):
    """xAI Grok provider using xAI's OpenAI-compatible endpoint."""

    provider_name = "grok"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
        client: AsyncOpenAI | None = None,
    ) -> None:
        """Default base_url to xAI's API unless explicitly overridden."""
        super().__init__(
            api_key=api_key,
            base_url=base_url or GROK_DEFAULT_BASE_URL,
            timeout_seconds=timeout_seconds,
            client=client,
        )


class GeminiProvider(OpenAICompatibleProvider):
    """Google Gemini provider via Gemini's OpenAI-compatible API."""

    provider_name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
        client: AsyncOpenAI | None = None,
    ) -> None:
        """Default base_url to Gemini's OpenAI-compatible endpoint unless overridden."""
        super().__init__(
            api_key=api_key,
            base_url=base_url or GEMINI_OPENAI_BASE_URL,
            timeout_seconds=timeout_seconds,
            client=client,
        )
