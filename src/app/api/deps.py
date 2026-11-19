"""FastAPI dependencies for auth, services, and repositories."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMProvider
from app.repositories.health_repo import HealthRepository
from app.schemas.common import CurrentUser
from app.services.chat_service import ChatService
from app.services.health_service import HealthService

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUser:
    """Validate the bearer token and return the authenticated app user."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError
    return decode_access_token(credentials.credentials, settings)


def get_llm_provider() -> LLMProvider:
    """Provide the configured provider abstraction (currently a safe stub)."""
    # TODO(phase-2): Select and configure a real provider based on LLM_PROVIDER.
    return AnthropicProvider()


def get_chat_service(
    provider: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> ChatService:
    """Construct a chat service using the provider dependency."""
    return ChatService(provider)


async def get_health_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> HealthService:
    """Construct the readiness service with a repository-backed DB check."""
    return HealthService(HealthRepository(session))


async def rate_limit_placeholder(
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Reserve a dependency slot for a shared rate limiter without false enforcement."""
    # TODO(phase-2): Add Redis-backed rate limiting and cache shared state.
    _ = settings.rate_limit_per_minute
