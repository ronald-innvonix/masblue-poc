"""FastAPI dependencies for auth, services, and repositories."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.llm.base import LLMProvider
from app.llm.factory import LLMFactory, ResolvedLLM
from app.repositories.health_repo import HealthRepository
from app.schemas.common import CurrentUser
from app.services.chat_service import ChatService
from app.services.health_service import HealthService

bearer_scheme = HTTPBearer(auto_error=False)

_ProviderCacheKey = tuple[str, str | None, str | None, str, float, int | None, float]
_chat_llm_cache: dict[_ProviderCacheKey, ResolvedLLM] = {}
_intent_llm_cache: dict[_ProviderCacheKey, ResolvedLLM] = {}


def _chat_cache_key(settings: Settings) -> _ProviderCacheKey:
    """Build a cache key for the configured chat LLM client."""
    return (
        settings.llm_provider,
        settings.llm_base_url,
        settings.llm_api_key,
        settings.llm_model,
        settings.llm_temperature,
        settings.llm_max_tokens,
        settings.llm_timeout_seconds,
    )


def _intent_cache_key(settings: Settings) -> _ProviderCacheKey:
    """Build a cache key for the configured intent-classification LLM client."""
    return (
        settings.intent_llm_provider or settings.llm_provider,
        settings.intent_llm_base_url or settings.llm_base_url,
        settings.intent_llm_api_key or settings.llm_api_key,
        settings.intent_llm_model or settings.llm_model,
        settings.intent_llm_temperature,
        settings.intent_llm_max_tokens,
        settings.intent_llm_timeout_seconds or settings.llm_timeout_seconds,
    )


async def dispose_llm_clients() -> None:
    """Close cached LLM provider clients during application shutdown."""
    cached = [*_chat_llm_cache.values(), *_intent_llm_cache.values()]
    _chat_llm_cache.clear()
    _intent_llm_cache.clear()
    for resolved in cached:
        await resolved.provider.close()


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


def get_chat_llm(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ResolvedLLM:
    """Provide the configured chat LLM provider and ModelConfig."""
    key = _chat_cache_key(settings)
    resolved = _chat_llm_cache.get(key)
    if resolved is None:
        resolved = LLMFactory.get_chat_llm(settings)
        _chat_llm_cache[key] = resolved
    return resolved


def get_intent_llm(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ResolvedLLM:
    """Provide the configured intent-classification LLM provider and ModelConfig."""
    key = _intent_cache_key(settings)
    resolved = _intent_llm_cache.get(key)
    if resolved is None:
        resolved = LLMFactory.get_intent_llm(settings)
        _intent_llm_cache[key] = resolved
    return resolved


def get_llm_provider(
    resolved: Annotated[ResolvedLLM, Depends(get_chat_llm)],
) -> LLMProvider:
    """Provide the configured primary LLMProvider instance."""
    return resolved.provider


def get_chat_service(
    resolved: Annotated[ResolvedLLM, Depends(get_chat_llm)],
) -> ChatService:
    """Construct a chat service using the resolved LLM provider and config."""
    return ChatService(resolved.provider, resolved.config)


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
