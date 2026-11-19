"""Shared test configuration and FastAPI client fixtures."""

import os
from collections.abc import AsyncIterator, Iterator

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://localhost/ai_chat")
os.environ["JWT_SECRET"] = "test-only-signing-secret"
os.environ.setdefault("APP_ENV", "test")

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Create a test client whose lifespan initializes and disposes resources."""
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Return a signed test token in the service's expected bearer format."""
    token = jwt.encode(
        {"sub": "00000000-0000-0000-0000-000000000001"},
        "test-only-signing-secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def test_db_session() -> AsyncIterator[AsyncSession]:
    """Provide an isolated async DB session for tests that exercise persistence."""
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        connect_args={"server_settings": {"search_path": settings.db_schema}},
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()
