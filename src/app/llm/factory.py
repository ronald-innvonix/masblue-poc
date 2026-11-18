from collections.abc import AsyncIterator

import structlog

from app.core.config import Settings, get_settings
from app.core.errors import TransientProviderError
from app.llm.base import LLMProvider, LLMResponse
from app.llm.providers.anthropic import AnthropicProvider
from app.llm.providers.openai import OpenAIProvider
from app.llm.providers.openai_compatible import OpenAICompatibleProvider

logger = structlog.get_logger(__name__)


def _build_provider(
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
    settings: Settings,
) -> LLMProvider:
    if provider == "anthropic":
        if not api_key:
            raise ValueError("Anthropic API key is required")
        return AnthropicProvider(
            model, api_key, settings.llm_timeout_seconds, settings.llm_max_retries
        )
    if provider == "openai":
        return OpenAIProvider(
            model, api_key, settings.llm_timeout_seconds, settings.llm_max_retries
        )
    if provider == "openai_compatible":
        if not base_url:
            raise ValueError("Base URL is required for openai_compatible")
        return OpenAICompatibleProvider(
            model, api_key, base_url, settings.llm_timeout_seconds, settings.llm_max_retries
        )
    raise ValueError(f"Unsupported LLM provider: {provider}")


class FallbackLLMProvider(LLMProvider):
    def __init__(self, primary: LLMProvider, fallback: LLMProvider | None) -> None:
        self.primary = primary
        self.fallback = fallback

    async def complete(
        self, system: str, messages: list[dict[str, str]], max_tokens: int, temperature: float
    ) -> LLMResponse:
        try:
            return await self.primary.complete(system, messages, max_tokens, temperature)
        except TransientProviderError:
            if self.fallback is None:
                raise
            logger.warning("llm_fallback_used")
            return await self.fallback.complete(system, messages, max_tokens, temperature)

    async def stream(
        self, system: str, messages: list[dict[str, str]], max_tokens: int, temperature: float
    ) -> AsyncIterator[str]:
        emitted = False
        try:
            async for token in self.primary.stream(system, messages, max_tokens, temperature):
                emitted = True
                yield token
        except TransientProviderError:
            if self.fallback is None:
                raise
            if not emitted:
                logger.warning("llm_fallback_used")
                async for token in self.fallback.stream(system, messages, max_tokens, temperature):
                    yield token
                return
            raise


def get_llm(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    primary = _build_provider(
        settings.llm_provider,
        settings.llm_model,
        settings.llm_api_key.get_secret_value() if settings.llm_api_key else None,
        settings.llm_base_url,
        settings,
    )
    fallback = None
    if settings.llm_fallback_provider and settings.llm_fallback_model:
        fallback = _build_provider(
            settings.llm_fallback_provider,
            settings.llm_fallback_model,
            (
                settings.llm_fallback_api_key.get_secret_value()
                if settings.llm_fallback_api_key
                else None
            ),
            settings.llm_fallback_base_url,
            settings,
        )
    return FallbackLLMProvider(primary, fallback)
