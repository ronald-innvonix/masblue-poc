from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import chat, health, ingest
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import bind_request_id, configure_logging
from app.core.rate_limit import build_rate_limiter
from app.db.repositories.chat_repository import ChatRepository
from app.db.session import SessionFactory, engine
from app.embeddings.factory import get_embeddings
from app.llm.factory import get_llm


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    embeddings = get_embeddings(settings)
    llm = get_llm(settings)
    async with SessionFactory() as session:
        dimension = await ChatRepository(session).vector_dimension()
    if dimension is None:
        raise RuntimeError("policy_chunks.embedding pgvector dimension could not be determined")
    if dimension != settings.embed_dim:
        raise RuntimeError(
            f"EMBED_DIM ({settings.embed_dim}) does not match policy_chunks.embedding ({dimension})"
        )
    app.state.embeddings = embeddings
    app.state.llm = llm
    app.state.rate_limiter = build_rate_limiter(settings)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Insurance Chat Service", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Internal-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.middleware("http")(bind_request_id)
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(ingest.router)
    register_error_handlers(app)
    return app


app = create_app()
