"""Authenticated chat and server-sent event endpoints."""

import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import get_chat_service, get_current_user, rate_limit_placeholder
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.common import CurrentUser
from app.services.chat_service import ChatService

router = APIRouter(
    dependencies=[Depends(rate_limit_placeholder)],
)


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ChatResponse:
    """Return a stubbed assistant reply for an authenticated request."""
    answer = await service.generate_reply(payload.message, user)
    return ChatResponse(conversation_id=payload.conversation_id, message=answer)


@router.post("/stream")
async def stream_chat(
    payload: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> StreamingResponse:
    """Stream fake assistant tokens using the browser-compatible SSE format."""

    async def event_stream() -> AsyncIterator[str]:
        """Encode provider token chunks as SSE data frames."""
        async for token in service.stream_reply(payload.message, user):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"

    # Disable proxy buffering so clients can paint each chunk as it arrives.
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
