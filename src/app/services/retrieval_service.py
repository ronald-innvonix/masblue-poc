from collections.abc import Sequence
from dataclasses import dataclass

from app.core.errors import ProviderError
from app.db.repositories.chat_repository import ChatRepository
from app.llm.base import EmbeddingProvider


@dataclass(frozen=True)
class RetrievedChunk:
    policy_id: str
    document_id: str
    chunk_index: int
    content: str
    section: str | None
    page_number: int
    score: float


class RetrievalService:
    def __init__(
        self,
        repository: ChatRepository,
        embeddings: EmbeddingProvider,
        top_k: int,
        expected_dimension: int,
    ) -> None:
        self.repository = repository
        self.embeddings = embeddings
        self.top_k = top_k
        self.expected_dimension = expected_dimension

    async def retrieve(
        self, user_id: str, policy_ids: Sequence[str] | None, query: str
    ) -> list[RetrievedChunk]:
        vectors = await self.embeddings.embed([query])
        if len(vectors) != 1 or len(vectors[0]) != self.expected_dimension:
            raise ProviderError("Embedding provider returned an unexpected vector dimension")
        rows = await self.repository.retrieve_chunks(user_id, policy_ids, vectors[0], self.top_k)
        return [
            RetrievedChunk(
                policy_id=chunk.policy_id,
                document_id=str(chunk.document_id),
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                section=chunk.section,
                page_number=chunk.page_number,
                score=1.0 - score,
            )
            for chunk, score in rows
        ]
