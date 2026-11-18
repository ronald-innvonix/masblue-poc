import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.errors import ProviderError
from app.llm.base import EmbeddingProvider


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self, model: str, api_key: str, base_url: str, timeout: float, max_retries: int
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    async def embed(self, texts: list[str]) -> list[list[float]]:
        @retry(
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
            stop=stop_after_attempt(self.max_retries + 1),
            wait=wait_exponential(multiplier=0.4, min=0.4, max=4),
            reraise=True,
        )
        async def send() -> list[list[float]]:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model, "input": texts},
                )
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        "Embedding provider server error",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                return [item["embedding"] for item in response.json()["data"]]

        try:
            return await send()
        except httpx.HTTPError as exc:
            raise ProviderError("Embedding provider request failed") from exc
