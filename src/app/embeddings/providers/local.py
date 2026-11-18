import asyncio
from typing import cast

from sentence_transformers import SentenceTransformer

from app.core.errors import ProviderError
from app.llm.base import EmbeddingProvider


class LocalEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model: str) -> None:
        self.model = SentenceTransformer(model)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            embeddings = await asyncio.to_thread(
                self.model.encode, texts, convert_to_numpy=True, normalize_embeddings=True
            )
            return cast(list[list[float]], embeddings.tolist())
        except (RuntimeError, ValueError) as exc:
            raise ProviderError("Local embedding generation failed") from exc
