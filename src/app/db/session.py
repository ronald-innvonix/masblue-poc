"""Create and manage the async SQLAlchemy engine and request sessions."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def initialize_database() -> None:
    """Initialize the process engine during application startup."""
    global _engine, _session_factory
    if _engine is not None:
        return
    settings = get_settings()
    _engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"server_settings": {"search_path": settings.db_schema}},
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def dispose_database() -> None:
    """Dispose the process engine during graceful application shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped async session and always close it afterward."""
    if _session_factory is None:
        raise RuntimeError("Database is not initialized; application lifespan is not active")
    async with _session_factory() as session:
        # Request-scoped sessions prevent concurrent requests sharing transaction state.
        yield session
