from typing import Any, cast

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.errors import ProviderError, TransientProviderError


def is_transient_http_error(error: BaseException) -> bool:
    return isinstance(error, (httpx.TimeoutException, httpx.TransportError)) or (
        isinstance(error, httpx.HTTPStatusError) and error.response.status_code >= 500
    )


def retry_policy(max_retries: int) -> Any:
    return retry(
        retry=retry_if_exception(is_transient_http_error),
        stop=stop_after_attempt(max_retries + 1),
        wait=wait_exponential(multiplier=0.4, min=0.4, max=4),
        reraise=True,
    )


async def open_event_stream(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
    retries: int,
) -> tuple[httpx.AsyncClient, httpx.Response]:
    async def open_once() -> tuple[httpx.AsyncClient, httpx.Response]:
        client = httpx.AsyncClient(timeout=timeout_seconds)
        try:
            request = client.build_request("POST", url, headers=headers, json=payload)
            response = await client.send(request, stream=True)
            response.raise_for_status()
            return client, response
        except BaseException:
            await client.aclose()
            raise

    try:
        return cast(
            tuple[httpx.AsyncClient, httpx.Response],
            await retry_policy(retries)(open_once)(),
        )
    except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
        if is_transient_http_error(exc):
            raise TransientProviderError("LLM provider stream request failed") from exc
        raise ProviderError("LLM provider rejected the stream request") from exc
