"""Unit tests for LLM providers, factory resolution, and chat/streaming wiring."""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from anthropic import APIConnectionError as AnthropicConnectionError
from fastapi.testclient import TestClient
from openai import APIConnectionError as OpenAIConnectionError

from app.api.deps import get_chat_llm
from app.core.config import Settings
from app.core.exceptions import LLMProviderError, ServiceConfigurationError
from app.llm import (
    AnthropicProvider,
    ChatMessage,
    GeminiProvider,
    GrokProvider,
    LLMFactory,
    LLMProvider,
    ModelConfig,
    OpenAICompatibleProvider,
    OpenAIProvider,
    ResolvedLLM,
    StubProvider,
)
from app.main import create_app


class _FakeAsyncOpenAI:
    """Minimal AsyncOpenAI test double supporting generate and stream."""

    def __init__(
        self,
        *,
        reply: str = "OpenAI reply",
        tokens: tuple[str, ...] = ("Hello ", "world"),
        error: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._reply = reply
        self._tokens = tokens
        self._error = error
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        if kwargs.get("stream"):

            async def _gen() -> AsyncIterator[Any]:
                for token in self._tokens:
                    yield SimpleNamespace(
                        choices=[SimpleNamespace(delta=SimpleNamespace(content=token))]
                    )

            return _gen()
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._reply))]
        )

    async def close(self) -> None:
        return None


class _FakeAsyncAnthropic:
    """Minimal AsyncAnthropic test double supporting create and stream."""

    def __init__(
        self,
        *,
        reply: str = "Claude reply",
        tokens: tuple[str, ...] = ("Hi ", "from ", "Claude"),
        error: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._reply = reply
        self._tokens = tokens
        self._error = error
        self.messages = SimpleNamespace(create=self._create, stream=self._stream)

    async def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self._reply)])

    def _stream(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        tokens = self._tokens
        error = self._error

        class _StreamCtx:
            async def __aenter__(self) -> Any:
                if error is not None:
                    raise error

                async def _text_gen() -> AsyncIterator[str]:
                    for token in tokens:
                        yield token

                return SimpleNamespace(text_stream=_text_gen())

            async def __aexit__(self, *_: object) -> None:
                return None

        return _StreamCtx()

    async def close(self) -> None:
        return None


class _FakeProvider(LLMProvider):
    """In-memory LLMProvider for testing FastAPI chat and stream endpoints."""

    def __init__(
        self,
        *,
        reply: str = "Live provider reply",
        tokens: tuple[str, ...] = ("Live ", "token"),
        fail: bool = False,
    ) -> None:
        self._reply = reply
        self._tokens = tokens
        self._fail = fail
        self.seen_messages: list[ChatMessage] = []
        self.seen_config: ModelConfig | None = None

    async def generate(self, messages: list[ChatMessage], config: ModelConfig) -> str:
        self.seen_messages = messages
        self.seen_config = config
        if self._fail:
            raise LLMProviderError("Provider unavailable")
        return self._reply

    async def _gen(self) -> AsyncIterator[str]:
        if self._fail:
            raise LLMProviderError("Stream interrupted")
        for token in self._tokens:
            yield token

    def stream(self, messages: list[ChatMessage], config: ModelConfig) -> AsyncIterator[str]:
        self.seen_messages = messages
        self.seen_config = config
        return self._gen()


def test_factory_resolves_supported_providers() -> None:
    """Verify LLMFactory builds the configured chat and intent providers."""
    assert isinstance(LLMFactory.get_chat_provider(Settings(llm_provider="stub")), StubProvider)

    grok = LLMFactory.get_chat_llm(
        Settings(
            llm_provider="grok",
            llm_api_key="xai-test",
            llm_model="grok-2",
            llm_temperature=0.2,
            intent_llm_provider="openai",
            intent_llm_api_key="sk-intent",
            intent_llm_model="gpt-4o-mini",
        )
    )
    assert isinstance(grok.provider, GrokProvider)
    assert grok.config.model == "grok-2"
    assert grok.config.temperature == 0.2

    intent = LLMFactory.get_intent_llm(
        Settings(
            llm_provider="grok",
            llm_api_key="xai-test",
            llm_model="grok-2",
            intent_llm_provider="openai",
            intent_llm_api_key="sk-intent",
            intent_llm_model="gpt-4o-mini",
        )
    )
    assert isinstance(intent.provider, OpenAIProvider)
    assert intent.config.model == "gpt-4o-mini"

    assert isinstance(
        LLMFactory.get_chat_provider(
            Settings(llm_provider="anthropic", llm_api_key="ant-test", llm_model="claude-sonnet-4")
        ),
        AnthropicProvider,
    )
    assert isinstance(
        LLMFactory.get_chat_provider(
            Settings(llm_provider="gemini", llm_api_key="gem-test", llm_model="gemini-2.5-flash")
        ),
        GeminiProvider,
    )
    assert isinstance(
        LLMFactory.get_chat_provider(
            Settings(
                llm_provider="openai_compatible",
                llm_base_url="http://localhost:11434/v1",
                llm_model="llama3.2",
            )
        ),
        OpenAICompatibleProvider,
    )


def test_factory_rejects_missing_credentials_or_unknown_provider() -> None:
    """Verify invalid provider configurations raise ServiceConfigurationError."""
    with pytest.raises(ServiceConfigurationError):
        LLMFactory.get_chat_llm(Settings(llm_provider="unknown", llm_model="m"))

    with pytest.raises(ServiceConfigurationError):
        LLMFactory.get_chat_llm(Settings(llm_provider="openai", llm_api_key=None, llm_model="gpt"))

    with pytest.raises(ServiceConfigurationError):
        LLMFactory.get_chat_llm(Settings(llm_provider="grok", llm_api_key="k", llm_model="stub"))

    with pytest.raises(ServiceConfigurationError):
        LLMFactory.get_chat_llm(
            Settings(llm_provider="openai_compatible", llm_base_url=None, llm_model="local")
        )


async def test_openai_compatible_provider_generate_and_stream() -> None:
    """Verify OpenAICompatibleProvider formats messages, streams tokens, and wraps errors."""
    fake_client = _FakeAsyncOpenAI()
    provider = GrokProvider(api_key="test-key", client=fake_client)  # type: ignore[arg-type]
    config = ModelConfig(model="grok-2", temperature=0.1, max_tokens=256)
    messages = [
        ChatMessage(role="system", content="Be concise."),
        ChatMessage(role="user", content="Hello"),
    ]

    result = await provider.generate(messages, config)
    assert result == "OpenAI reply"
    assert fake_client.calls[0]["model"] == "grok-2"
    assert fake_client.calls[0]["max_tokens"] == 256

    chunks = [token async for token in provider.stream(messages, config)]
    assert chunks == ["Hello ", "world"]

    failing_client = _FakeAsyncOpenAI(
        error=OpenAIConnectionError(request=httpx.Request("POST", "https://api.x.ai/v1"))
    )
    failing_provider = GrokProvider(api_key="test-key", client=failing_client)  # type: ignore[arg-type]
    with pytest.raises(LLMProviderError):
        await failing_provider.generate(messages, config)


async def test_anthropic_provider_generate_and_stream() -> None:
    """Verify AnthropicProvider extracts system messages, streams text, and wraps errors."""
    fake_client = _FakeAsyncAnthropic()
    provider = AnthropicProvider(api_key="test-key", client=fake_client)  # type: ignore[arg-type]
    config = ModelConfig(model="claude-sonnet-4", temperature=0.0)
    messages = [
        ChatMessage(role="system", content="You help policyholders."),
        ChatMessage(role="user", content="What is covered?"),
    ]

    result = await provider.generate(messages, config)
    assert result == "Claude reply"
    assert fake_client.calls[0]["system"] == "You help policyholders."
    assert fake_client.calls[0]["messages"] == [{"role": "user", "content": "What is covered?"}]

    chunks = [token async for token in provider.stream(messages, config)]
    assert chunks == ["Hi ", "from ", "Claude"]

    failing_client = _FakeAsyncAnthropic(
        error=AnthropicConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    )
    failing_provider = AnthropicProvider(api_key="test-key", client=failing_client)  # type: ignore[arg-type]
    with pytest.raises(LLMProviderError):
        async for _ in failing_provider.stream(messages, config):
            pass


def test_chat_and_stream_endpoints_use_resolved_provider(
    auth_headers: dict[str, str],
) -> None:
    """Verify /chat and /chat/stream invoke the configured LLMProvider and ModelConfig."""
    fake_provider = _FakeProvider()
    app = create_app()
    app.dependency_overrides[get_chat_llm] = lambda: ResolvedLLM(
        provider=fake_provider,
        config=ModelConfig(model="grok-2", temperature=0.0),
    )

    with TestClient(app) as test_client:
        chat_resp = test_client.post(
            "/api/v1/chat",
            headers=auth_headers,
            json={"message": "Explain my deductible"},
        )
        assert chat_resp.status_code == 200
        assert chat_resp.json()["message"] == "Live provider reply"
        assert fake_provider.seen_config == ModelConfig(model="grok-2", temperature=0.0)
        assert fake_provider.seen_messages[-1] == ChatMessage(
            role="user",
            content="Explain my deductible",
        )

        stream_resp = test_client.post(
            "/api/v1/chat/stream",
            headers=auth_headers,
            json={"message": "Stream please"},
        )
        assert stream_resp.status_code == 200
        assert 'data: {"token": "Live "}' in stream_resp.text
        assert 'data: {"token": "token"}' in stream_resp.text
        assert "data: [DONE]" in stream_resp.text


def test_chat_and_stream_endpoints_handle_provider_errors(
    auth_headers: dict[str, str],
) -> None:
    """Verify /chat returns 502 JSON error and /chat/stream emits an SSE error frame."""
    failing_provider = _FakeProvider(fail=True)
    app = create_app()
    app.dependency_overrides[get_chat_llm] = lambda: ResolvedLLM(
        provider=failing_provider,
        config=ModelConfig(model="grok-2"),
    )

    with TestClient(app) as test_client:
        chat_resp = test_client.post(
            "/api/v1/chat",
            headers=auth_headers,
            json={"message": "Fail"},
        )
        assert chat_resp.status_code == 502
        assert chat_resp.json()["error"]["code"] == "LLM_PROVIDER_ERROR"

        stream_resp = test_client.post(
            "/api/v1/chat/stream",
            headers=auth_headers,
            json={"message": "Fail stream"},
        )
        assert stream_resp.status_code == 200
        assert '"code": "LLM_PROVIDER_ERROR"' in stream_resp.text
        assert "data: [DONE]" in stream_resp.text
