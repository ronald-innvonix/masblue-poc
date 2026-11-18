from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.repositories.chat_repository import ChatRepository
from app.db.session import get_session
from app.llm.base import EmbeddingProvider, LLMProvider
from app.services.chat_service import ChatService
from app.services.ingestion_service import IngestionService
from app.services.retrieval_service import RetrievalService

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_llm_provider(request: Request) -> LLMProvider:
    return cast(LLMProvider, request.app.state.llm)


def get_embedding_provider(request: Request) -> EmbeddingProvider:
    return cast(EmbeddingProvider, request.app.state.embeddings)


def get_chat_service(
    session: SessionDep,
    settings: SettingsDep,
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
    embeddings: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
) -> ChatService:
    retrieval = RetrievalService(
        repository=ChatRepository(session),
        embeddings=embeddings,
        top_k=settings.retrieval_top_k,
        expected_dimension=settings.embed_dim,
    )
    return ChatService(session, llm, retrieval, settings)


def get_ingestion_service(
    session: SessionDep,
    embeddings: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
) -> IngestionService:
    return IngestionService(session, embeddings)
