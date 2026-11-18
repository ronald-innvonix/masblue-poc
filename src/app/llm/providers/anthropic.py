import json
import time
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx
import structlog

from app.core.errors import ProviderError, TransientProviderError
from app.llm.base import LLMProvider, LLMResponse
from app.llm.transport import is_transient_http_error, open_event_stream, retry_policy

logger = structlog.get_logger(__name__)


class AnthropicProvider(LLMProvider):
    def __init__(self, model: str, api_key: str, timeout: float, max_retries: int) -> None:
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        async def send() -> httpx.Response:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=payload,
                )
                if response.status_code >= 500:
                    response.raise_for_status()
                response.raise_for_status()
                return response

        try:
            return cast(httpx.Response, await retry_policy(self.max_retries)(send)())
        except (httpx.HTTPError, TimeoutError) as exc:
            if is_transient_http_error(exc) or isinstance(exc, TimeoutError):
                raise TransientProviderError("LLM provider request failed") from exc
            raise ProviderError("LLM provider request failed") from exc

    async def complete(
        self, system: str, messages: list[dict[str, str]], max_tokens: int, temperature: float
    ) -> LLMResponse:
        started = time.monotonic()
        data = (
            await self._post(
                {
                    "model": self.model,
                    "system": system,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
            )
        ).json()
        result = LLMResponse(
            text="".join(part["text"] for part in data["content"] if part["type"] == "text"),
            model=self.model,
            input_tokens=data.get("usage", {}).get("input_tokens", 0),
            output_tokens=data.get("usage", {}).get("output_tokens", 0),
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        logger.info(
            "llm_call",
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=result.latency_ms,
        )
        return result

    async def stream(
        self, system: str, messages: list[dict[str, str]], max_tokens: int, temperature: float
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        client, response = await open_event_stream(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            payload,
            self.timeout,
            self.max_retries,
        )
        try:
            try:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        event = json.loads(line[6:])
                        if event.get("type") == "content_block_delta":
                            text = event.get("delta", {}).get("text")
                            if text:
                                yield text
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                raise TransientProviderError("LLM provider stream interrupted") from exc
        finally:
            await response.aclose()
            await client.aclose()
