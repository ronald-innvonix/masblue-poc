"""Factory for constructing configured chat and intent LLM providers."""

from dataclasses import dataclass

from app.core.config import Settings
from app.core.exceptions import ServiceConfigurationError
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMProvider, ModelConfig
from app.llm.openai_provider import (
    GeminiProvider,
    GrokProvider,
    OpenAICompatibleProvider,
    OpenAIProvider,
)
from app.llm.stub_provider import StubProvider

_OPENAI_COMPATIBLE_PROVIDERS: dict[str, type[OpenAICompatibleProvider]] = {
    "openai": OpenAIProvider,
    "grok": GrokProvider,
    "gemini": GeminiProvider,
    "openai_compatible": OpenAICompatibleProvider,
}


@dataclass(frozen=True, slots=True)
class ResolvedLLM:
    """A concrete LLM provider paired with its resolved ModelConfig."""

    provider: LLMProvider
    config: ModelConfig


class LLMFactory:
    """Resolve provider implementations and configs from runtime Settings."""

    @staticmethod
    def _build_provider(
        *,
        provider_name: str,
        api_key: str | None,
        base_url: str | None,
        model: str,
        timeout_seconds: float,
    ) -> LLMProvider:
        """Instantiate the requested LLMProvider and validate required settings."""
        normalized = provider_name.strip().lower()
        if normalized == "stub":
            return StubProvider()

        cleaned_model = model.strip()
        if not cleaned_model or cleaned_model.lower() == "stub":
            raise ServiceConfigurationError

        cleaned_base_url = base_url.strip() if base_url else None
        cleaned_api_key = api_key.strip() if api_key else None

        if normalized == "anthropic":
            if not cleaned_api_key:
                raise ServiceConfigurationError
            return AnthropicProvider(
                api_key=cleaned_api_key,
                base_url=cleaned_base_url,
                timeout_seconds=timeout_seconds,
            )

        provider_cls = _OPENAI_COMPATIBLE_PROVIDERS.get(normalized)
        if provider_cls is None:
            raise ServiceConfigurationError

        if normalized == "openai_compatible":
            if not cleaned_base_url:
                raise ServiceConfigurationError
            # Local OpenAI-compatible servers (Ollama/vLLM) may not require a real key.
            effective_key = cleaned_api_key or "local-dev-key"
            return provider_cls(
                api_key=effective_key,
                base_url=cleaned_base_url,
                timeout_seconds=timeout_seconds,
            )

        if not cleaned_api_key:
            raise ServiceConfigurationError

        return provider_cls(
            api_key=cleaned_api_key,
            base_url=cleaned_base_url,
            timeout_seconds=timeout_seconds,
        )

    @classmethod
    def get_chat_llm(cls, settings: Settings) -> ResolvedLLM:
        """Build the primary chat/reasoning provider and its ModelConfig."""
        config = ModelConfig(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout_seconds=settings.llm_timeout_seconds,
        )
        provider = cls._build_provider(
            provider_name=settings.llm_provider,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
        return ResolvedLLM(provider=provider, config=config)

    @classmethod
    def get_intent_llm(cls, settings: Settings) -> ResolvedLLM:
        """Build the intent-classification provider and its ModelConfig."""
        provider_name = settings.intent_llm_provider or settings.llm_provider
        model = settings.intent_llm_model or settings.llm_model
        api_key = settings.intent_llm_api_key or settings.llm_api_key
        base_url = settings.intent_llm_base_url or settings.llm_base_url
        timeout_seconds = settings.intent_llm_timeout_seconds or settings.llm_timeout_seconds

        config = ModelConfig(
            model=model,
            temperature=settings.intent_llm_temperature,
            max_tokens=settings.intent_llm_max_tokens,
            timeout_seconds=timeout_seconds,
        )
        provider = cls._build_provider(
            provider_name=provider_name,
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
        )
        return ResolvedLLM(provider=provider, config=config)

    @classmethod
    def get_chat_provider(cls, settings: Settings) -> LLMProvider:
        """Return only the configured chat LLMProvider."""
        return cls.get_chat_llm(settings).provider

    @classmethod
    def get_intent_provider(cls, settings: Settings) -> LLMProvider:
        """Return only the configured intent LLMProvider."""
        return cls.get_intent_llm(settings).provider
