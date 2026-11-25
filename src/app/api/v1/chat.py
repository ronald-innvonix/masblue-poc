"""Authenticated chat and server-sent event endpoints."""

import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_chat_service, get_current_user, rate_limit_placeholder
from app.core.exceptions import AppError
from app.db.session import get_db
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.message_repo import MessageRepository
from app.schemas.chat import ChatRequest, ChatResponse, ConversationMessagesResponse
from app.schemas.common import CurrentUser
from app.services.chat_service import ChatService

logger = structlog.get_logger(__name__)

router = APIRouter(
    dependencies=[Depends(rate_limit_placeholder)],
)


@router.get("/{conversation_id}/messages", response_model=ConversationMessagesResponse)
async def get_conversation_messages(
    conversation_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ConversationMessagesResponse:
    """Return an authenticated user's conversation messages in chronological pages."""
    conversation = await ConversationRepository(session).get_for_user(
        conversation_id,
        user.user_id,
    )
    if conversation is None:
        raise AppError("CONVERSATION_NOT_FOUND", "Conversation not found", 404)

    messages, total = await MessageRepository(session).list_page_for_conversation(
        conversation_id,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return ConversationMessagesResponse(
        conversation_id=conversation_id,
        page=page,
        page_size=page_size,
        total=total,
        messages=messages,
    )


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ChatResponse:
    """Return an assistant reply for an authenticated request."""
    conversation_id, answer = await service.generate_reply(
        payload.message,
        user,
        payload.conversation_id,
    )
    return ChatResponse(conversation_id=conversation_id, message=answer)


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
            async for event in service.stream_reply(
                payload.message,
                user,
                payload.conversation_id,
            ):
                yield f"data: {json.dumps(event)}\n\n"
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
