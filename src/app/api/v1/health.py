from fastapi import APIRouter, Request

from app.db.repositories.chat_repository import ChatRepository
from app.db.session import SessionFactory

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "live"}


@router.get("/health/ready")
async def ready(request: Request) -> dict[str, str]:
    async with SessionFactory() as session:
        await ChatRepository(session).ping()
    if not hasattr(request.app.state, "llm") or not hasattr(request.app.state, "embeddings"):
        raise RuntimeError("Application providers are not initialized")
    return {"status": "ready"}
