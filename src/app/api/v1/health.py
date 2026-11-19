"""Liveness and database-readiness probes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_health_service
from app.services.health_service import HealthService

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Return a lightweight liveness response without checking dependencies."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(
    service: Annotated[HealthService, Depends(get_health_service)],
) -> dict[str, str]:
    """Check that the service can reach its own PostgreSQL schema."""
    await service.check_database()
    return {"status": "ready"}
