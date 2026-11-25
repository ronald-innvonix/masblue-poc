"""Authenticated chat and server-sent event endpoints."""

import json
from collections.abc import AsyncIterator
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_chat_service, get_current_user, rate_limit_placeholder
from app.core.exceptions import AppError
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.common import CurrentUser
from app.services.chat_service import ChatService

logger = structlog.get_logger(__name__)

router = APIRouter(
    dependencies=[Depends(rate_limit_placeholder)],
)


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ChatResponse:
    """Return an assistant reply for an authenticated request."""
    answer = await service.generate_reply(payload.message, user)
    return ChatResponse(conversation_id=payload.conversation_id, message=answer)


@router.post("/stream")
async def stream_chat(
    request: Request,
    payload: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> StreamingResponse:
    """Stream assistant tokens using the browser-compatible SSE format."""
    request_id = str(getattr(request.state, "request_id", "unknown"))

    async def event_stream() -> AsyncIterator[str]:
        """Encode provider token chunks as SSE data frames."""
        try:
            async for token in service.stream_reply(payload.message, user):
                yield f"data: {json.dumps({'token': token})}\n\n"
        except AppError as exc:
            error_payload = {"error": {"code": exc.code, "message": exc.message}}
            yield f"data: {json.dumps(error_payload)}\n\n"
        except Exception as exc:
            logger.error(
                "stream_unhandled_exception",
                request_id=request_id,
                exception_type=type(exc).__name__,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            error_payload = {
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred",
                }
            }
            yield f"data: {json.dumps(error_payload)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    # Disable proxy buffering so clients can paint each chunk as it arrives.
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
