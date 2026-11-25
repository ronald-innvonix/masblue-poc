"""Seed the active Gemini conversation model into the model registry."""

import asyncio
from getpass import getpass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.embedding_model import EmbeddingModel, EmbeddingModelType

_GEMINI_CONVERSATION_MODEL = {
    "provider": "gemini",
    "base_url": None,
    "model_name": "gemini-3.1-flash-lite",
    "is_active": True,
    "type": EmbeddingModelType.CONVERSATION,
}


async def seed_models() -> None:
    """Upsert the manually configured Gemini conversation model."""
    settings = get_settings()
    model_data = {
        **_GEMINI_CONVERSATION_MODEL,
        "api_key": getpass("Gemini API key: "),
    }
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"server_settings": {"search_path": settings.db_schema}},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            await session.execute(
                update(EmbeddingModel)
                .where(
                    EmbeddingModel.type == EmbeddingModelType.CONVERSATION,
                    EmbeddingModel.is_active.is_(True),
                )
                .values(is_active=False)
            )
            result = await session.execute(
                select(EmbeddingModel).where(
                    EmbeddingModel.provider == model_data["provider"],
                    EmbeddingModel.model_name == model_data["model_name"],
                    EmbeddingModel.type == model_data["type"],
                )
            )
            model = result.scalar_one_or_none()
            if model is None:
                model = EmbeddingModel(**model_data)
                session.add(model)
            else:
                for field, value in model_data.items():
                    setattr(model, field, value)
            await session.commit()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_models())
