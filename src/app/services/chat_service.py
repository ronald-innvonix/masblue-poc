"""Chat use cases independent of HTTP and database details."""

from collections.abc import AsyncIterator
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.llm.base import ChatMessage, LLMProvider, ModelConfig
from app.models.conversation import Conversation
from app.models.message import Message
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.message_repo import MessageRepository
from app.schemas.common import CurrentUser

DEFAULT_CHAT_SYSTEM_PROMPT = (
    "You are the Masblue AI Assistant. Provide clear, concise, and helpful responses."
)


class ChatService:
    """Coordinate chat requests through the provider abstraction."""

    def __init__(
        self,
        provider: LLMProvider,
        model_config: ModelConfig,
        session: AsyncSession,
        conversations: ConversationRepository,
        messages: MessageRepository,
        system_prompt: str | None = DEFAULT_CHAT_SYSTEM_PROMPT,
    ) -> None:
        """Create a chat service with its injected LLM provider and model config."""
        self._provider = provider
        self._model_config = model_config
        self._session = session
        self._conversations = conversations
        self._messages = messages
        self._system_prompt = system_prompt

    async def _prepare_turn(
        self,
        message: str,
        user: CurrentUser,
        conversation_id: UUID | None,
    ) -> tuple[Conversation, list[Message]]:
        """Load or create the owned conversation and persist the incoming user turn."""
        user_id = user.user_id
        if conversation_id is None:
            conversation = await self._conversations.add(
                Conversation(user_id=user_id, title=message[:255]),
            )
        else:
            conversation = await self._conversations.get_for_user(conversation_id, user_id)
            if conversation is None:
                raise AppError("CONVERSATION_NOT_FOUND", "Conversation not found", 404)

        await self._messages.add(
            Message(conversation_id=conversation.id, role="user", content=message),
        )
        await self._session.commit()
        return conversation, await self._messages.list_for_conversation(conversation.id)

    def _build_messages(self, history: list[Message]) -> list[ChatMessage]:
        """Assemble the system prompt and persisted conversation history."""
        messages: list[ChatMessage] = []
        if self._system_prompt:
            messages.append(ChatMessage(role="system", content=self._system_prompt))
        messages.extend(
            ChatMessage(role=message.role, content=message.content)
            for message in history
            if message.role in ("user", "assistant", "system")
        )
        return messages

    async def generate_reply(
        self,
        message: str,
        user: CurrentUser,
        conversation_id: UUID | None = None,
    ) -> tuple[UUID, str]:
        """Generate and persist an assistant reply for an authenticated conversation."""
        conversation, history = await self._prepare_turn(message, user, conversation_id)
        answer = await self._provider.generate(self._build_messages(history), self._model_config)
        await self._messages.add(
            Message(conversation_id=conversation.id, role="assistant", content=answer),
        )
        await self._session.commit()
        return conversation.id, answer

    async def stream_reply(
        self,
        message: str,
        user: CurrentUser,
        conversation_id: UUID | None = None,
    ) -> AsyncIterator[dict[str, str]]:
        """Persist a user turn and yield its conversation ID followed by LLM chunks."""
        conversation, history = await self._prepare_turn(message, user, conversation_id)

        # This is deliberately the first yielded event, before the provider request starts.
        yield {"conversation_id": str(conversation.id)}

        answer_parts: list[str] = []
        async for token in self._provider.stream(
            self._build_messages(history),
            self._model_config,
        ):
            answer_parts.append(token)
            yield {"token": token}

        await self._messages.add(
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content="".join(answer_parts),
            ),
        )
        await self._session.commit()
