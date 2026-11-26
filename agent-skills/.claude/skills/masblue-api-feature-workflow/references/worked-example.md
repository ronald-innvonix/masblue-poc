# Worked example: `GET /api/v1/conversations`

A complete feature, built bottom-up, that passed `ruff check`, `ruff format --check`, and `pytest`
(3 new tests, no database needed) and added no mypy errors. Use it as the template for the shape,
naming, docstrings, and test style of new features. Replace "conversation" with your entity.

**Contract:** authenticated; returns the caller's conversations, newest first, paginated
(`page`, `page_size`); envelope `{page, page_size, total, conversations[]}`.

## Contents
1. Schema 2. Repository method 3. Service 4. Dependency 5. Route 6. Register router
7. Route tests 8. Service test 9. Adapting it to a write endpoint

---

## 1. Schema: `src/app/schemas/chat.py` (append)

```python
class ConversationItem(BaseModel):
    """A conversation summary returned by the conversation list API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    """Paginated conversations for the authenticated user, newest first."""

    page: int
    page_size: int
    total: int
    conversations: list[ConversationItem]
```

## 2. Repository method: `src/app/repositories/conversation_repo.py`

Also change the import line to `from sqlalchemy import func, select`. Add to the class:

```python
    async def list_page_for_user(
        self,
        user_id: str,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[Conversation], int]:
        """Return one page of a user's conversations (newest first) and their total count."""
        owned = Conversation.user_id == user_id
        result = await self._session.execute(
            select(Conversation)
            .where(owned)
            .order_by(Conversation.updated_at.desc(), Conversation.id)
            .offset(offset)
            .limit(limit)
        )
        count_result = await self._session.execute(
            select(func.count()).select_from(Conversation).where(owned)
        )
        return list(result.scalars().all()), count_result.scalar_one()
```

Notes: user scoping is in the `WHERE`; ordering has an `id` tiebreaker; paging is keyword-only; the
count query reuses the same filter; it returns a `(items, total)` tuple; no `commit()`.

## 3. Service: `src/app/services/conversation_service.py` (new file)

```python
"""Conversation history use cases."""

from app.models.conversation import Conversation
from app.repositories.conversation_repo import ConversationRepository
from app.schemas.common import CurrentUser


class ConversationService:
    """List and read an authenticated user's conversations."""

    def __init__(self, conversations: ConversationRepository) -> None:
        """Create a conversation service with its conversation repository."""
        self._conversations = conversations

    async def list_for_user(
        self,
        user: CurrentUser,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[Conversation], int]:
        """Return one page of the user's conversations and the total count."""
        return await self._conversations.list_page_for_user(
            user.user_id,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
```

## 4. Dependency: `src/app/api/deps.py`

Add the import `from app.services.conversation_service import ConversationService`, then:

```python
async def get_conversation_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationService:
    """Construct the conversation history service with its repository."""
    return ConversationService(ConversationRepository(session))
```

## 5. Route: `src/app/api/v1/conversations.py` (new file)

```python
"""Authenticated conversation history endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_conversation_service, get_current_user, rate_limit_placeholder
from app.schemas.chat import ConversationItem, ConversationListResponse
from app.schemas.common import CurrentUser
from app.services.conversation_service import ConversationService

router = APIRouter(
    dependencies=[Depends(rate_limit_placeholder)],
)


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    # Declared first so authentication runs before any database-backed dependency.
    user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[ConversationService, Depends(get_conversation_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ConversationListResponse:
    """Return the authenticated user's conversations in newest-first pages."""
    conversations, total = await service.list_for_user(user, page=page, page_size=page_size)
    return ConversationListResponse(
        page=page,
        page_size=page_size,
        total=total,
        conversations=[ConversationItem.model_validate(item) for item in conversations],
    )
```

Note the comment on parameter order: `user` is first so authentication runs before the
database-backed service dependency.

## 6. Register the router: `src/app/api/v1/router.py`

```python
from app.api.v1.conversations import router as conversations_router

api_router.include_router(conversations_router, prefix="/conversations", tags=["conversations"])
```

## 7. Route tests: `tests/unit/test_conversations.py` (new file)

Override the **service** dependency with a fake. The fake records its calls, so the test proves the
route passed the authenticated user and the paging arguments through. No database is touched because
the engine is created lazily and the service never queries.

```python
"""Unit tests for the conversation history API."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_conversation_service
from app.main import create_app
from app.models.conversation import Conversation
from app.schemas.common import CurrentUser


class _FakeConversationService:
    """In-memory ConversationService double recording the calls it receives."""

    def __init__(self, conversations: list[Conversation], total: int) -> None:
        self.calls: list[tuple[str, int, int]] = []
        self._conversations = conversations
        self._total = total

    async def list_for_user(
        self,
        user: CurrentUser,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[Conversation], int]:
        self.calls.append((user.user_id, page, page_size))
        return self._conversations, self._total


def _conversation(title: str) -> Conversation:
    now = datetime.now(UTC)
    return Conversation(id=uuid4(), user_id="u", title=title, created_at=now, updated_at=now)


def test_list_conversations_returns_paginated_items(auth_headers: dict[str, str]) -> None:
    """Verify the route passes the authenticated user and paging to the service."""
    fake = _FakeConversationService([_conversation("Hello")], total=1)
    app = create_app()
    app.dependency_overrides[get_conversation_service] = lambda: fake

    with TestClient(app) as test_client:
        response = test_client.get(
            "/api/v1/conversations?page=2&page_size=5",
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["conversations"][0]["title"] == "Hello"
    assert UUID(body["conversations"][0]["id"])
    assert fake.calls == [("00000000-0000-0000-0000-000000000001", 2, 5)]


def test_list_conversations_requires_bearer_token() -> None:
    """Verify unauthenticated requests are rejected before any service runs."""
    fake = _FakeConversationService([], total=0)
    app = create_app()
    app.dependency_overrides[get_conversation_service] = lambda: fake

    with TestClient(app) as test_client:
        response = test_client.get("/api/v1/conversations")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert fake.calls == []
```

## 8. Service test: `tests/unit/test_conversation_service.py` (new file)

A fake repository replaces the database. `async def` tests need no marker (`asyncio_mode = "auto"`).

```python
"""Unit tests for conversation history use cases."""

from datetime import UTC, datetime
from uuid import uuid4

from app.models.conversation import Conversation
from app.schemas.common import CurrentUser
from app.services.conversation_service import ConversationService


class _FakeConversationRepository:
    """In-memory repository double that records paging arguments."""

    def __init__(self, conversations: list[Conversation]) -> None:
        self.calls: list[tuple[str, int, int]] = []
        self._conversations = conversations

    async def list_page_for_user(
        self,
        user_id: str,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[Conversation], int]:
        self.calls.append((user_id, offset, limit))
        return self._conversations, len(self._conversations)


async def test_list_for_user_converts_page_to_offset() -> None:
    """Verify page numbers become zero-based offsets scoped to the caller."""
    now = datetime.now(UTC)
    conversation = Conversation(
        id=uuid4(), user_id="u-1", title="Hi", created_at=now, updated_at=now
    )
    repo = _FakeConversationRepository([conversation])
    service = ConversationService(repo)  # type: ignore[arg-type]
    user = CurrentUser(user_id="u-1", claims={})

    items, total = await service.list_for_user(user, page=3, page_size=10)

    assert repo.calls == [("u-1", 20, 10)]
    assert items == [conversation]
    assert total == 1
```

## 9. Adapting it to a write endpoint

For `POST`/`PUT`/`DELETE`, the service owns the transaction. Study `ChatService._prepare_turn` in
`src/app/services/chat_service.py` and follow its sequence:

1. Load or create the owned record through the repository (`get_for_user` or `add`).
2. Raise `AppError("<THING>_NOT_FOUND", "<Thing> not found", 404)` if absent or not owned.
3. Apply the change through repository calls (they `flush()`).
4. `await self._session.commit()` once, after the whole use case succeeded.

That means a write service's constructor takes the `AsyncSession` as well as the repositories, which
is why `get_chat_service` passes `session` in and `get_conversation_service` (read-only) does not.
