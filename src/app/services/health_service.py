"""Readiness use case."""

from app.repositories.health_repo import HealthRepository


class HealthService:
    """Expose dependency readiness without putting DB access in route handlers."""

    def __init__(self, repository: HealthRepository) -> None:
        """Create a readiness service with its database repository."""
        self._repository = repository

    async def check_database(self) -> None:
        """Verify the configured PostgreSQL connection is usable."""
        await self._repository.check_database()
