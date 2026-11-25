"""Database queries for configured chat and embedding models."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.embedding_model import EmbeddingModel, EmbeddingModelType


class ModelRepository:
    """Read model registry entries used by runtime services."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_by_type(self, model_type: EmbeddingModelType) -> EmbeddingModel | None:
        """Return the active registry entry for a model purpose, if configured."""
        result = await self._session.execute(
            select(EmbeddingModel).where(
                EmbeddingModel.type == model_type,
                EmbeddingModel.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()
