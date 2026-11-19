"""Database readiness query repository."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class HealthRepository:
    """Run minimal health checks against the service database."""

    def __init__(self, session: AsyncSession) -> None:
        """Store the request-scoped asynchronous database session."""
        self._session = session

    async def check_database(self) -> None:
        """Execute a lightweight query to verify database connectivity."""
        await self._session.execute(text("SELECT 1"))
