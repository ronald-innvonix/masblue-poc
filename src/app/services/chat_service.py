import asyncio
import json
import time
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ProviderError
from app.db.models import FieldGlossary
from app.db.repositories.chat_repository import ChatRepository
from app.llm.base import LLMProvider
from app.schemas.chat import ChatRequest, ChatResponse, ChatSource
from app.services.facts_service import FactsService
from app.services.intent_router import Intent, route_intent
from app.services.retrieval_service import RetrievalService

PROMPT_DIR = Path(__file__).parents[1] / "llm" / "prompts"
NO_POLICY_CONTEXT = "I couldn't find this information in your policy."
NO_FIELD_CONTEXT = "I couldn't find that field in the form glossary."
HANDOFF_MESSAGE = (
    "I can't make claim decisions or change your policy. Please contact your insurer or "
    "claims representative for help."
)
OTHER_USER_MESSAGE = "I can only provide information for policies associated with your account."
OTHER_USER_TERMS = (
    "another user's policy",
    "someone else's policy",
    "another person's policy",
    "other user's policy",
    "neighbor's policy",
    "friend's policy",
    "coworker's policy",
    "spouse's policy",
    "wife's policy",
    "husband's policy",
    "partner's policy",
)


async def _prompt(intent: Intent) -> str:
    prompt_path = PROMPT_DIR / f"{intent}_v1.txt"
    return await asyncio.to_thread(prompt_path.read_text, encoding="utf-8")


def _policy_targets(request: ChatRequest) -> list[str] | None:
    targets = list(request.policy_ids)
    if request.policy_id and request.policy_id not in targets:
        targets.append(request.policy_id)
    return targets or None


def _is_other_user_request(message: str) -> bool:
    normalized = message.lower().replace("’", "'")
    return any(phrase in normalized for phrase in OTHER_USER_TERMS)


class ChatService:
    def __init__(
        self,
        session: AsyncSession,
        llm: LLMProvider,
        retrieval: RetrievalService,
        settings: Settings,
    ) -> None:
        self.session = session
        self.repository = ChatRepository(session)
        self.llm = llm
        self.retrieval = retrieval
        self.facts = FactsService(self.repository)
        self.settings = settings

    async def _context(
        self, request: ChatRequest, intent: Intent
    ) -> tuple[str, list[ChatSource], bool]:
        if intent == "field_help":
            glossary: FieldGlossary | None = None
            if request.form_context is not None:
                glossary = await self.repository.get_glossary_field(
                    request.form_context.field.strip().casefold()
                )
            elif request.message:
                glossary_entries = await self.repository.find_glossary(request.message)
                glossary = glossary_entries[0] if glossary_entries else None
            if glossary is None:
                return "", [], False
            context = (
                f"Form: {request.form_context.form if request.form_context else 'unspecified'}\n"
                f"Field: {glossary.field_key} ({glossary.label})\n"
                f"Definition: {glossary.definition}"
            )
            return context, [], True

        if intent != "policy_qa":
            return "", [], False

        targets = _policy_targets(request)
        chunks = await self.retrieval.retrieve(request.user_id, targets, request.message)
        chunks = [chunk for chunk in chunks if chunk.score >= self.settings.retrieval_min_score]
        facts = await self.facts.for_policies(request.user_id, targets)
        context_parts = [
            (
                f"Policy {chunk.policy_id}; section {chunk.section or 'unspecified'}; "
                f"page {chunk.page_number} excerpt:\n{chunk.content}"
            )
            for chunk in chunks
        ]
        context_parts.extend(
            f"Policy {fact.policy_id}; database fact {fact.fact_key}: {fact.fact_value}"
            for fact in facts
        )
        sources = [
            ChatSource(
                policy_id=chunk.policy_id,
                document_id=chunk.document_id,
                chunk_index=chunk.chunk_index,
                excerpt=chunk.content[:300],
                section=chunk.section,
                page=chunk.page_number,
            )
            for chunk in chunks
        ]
        sources.extend(
            ChatSource(
                source_type="policy_fact",
                policy_id=fact.policy_id,
                excerpt=f"{fact.fact_key}: {fact.fact_value}",
                section=f"Structured fact: {fact.fact_key}",
            )
            for fact in facts
        )
        return "\n\n".join(context_parts), sources, bool(context_parts)

    async def _audit(
        self,
        request: ChatRequest,
        intent: Intent,
        answer: str,
        sources: list[ChatSource],
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
    ) -> None:
        await self.repository.add_audit(
            request.user_id,
            request.policy_id or (request.policy_ids[0] if len(request.policy_ids) == 1 else None),
            intent,
            request.message,
            answer,
            [source.model_dump() for source in sources],
            model,
            input_tokens,
            output_tokens,
            latency_ms,
        )

    def _messages(self, request: ChatRequest, context: str) -> list[dict[str, str]]:
        return [
            *[{"role": item.role, "content": item.content} for item in request.history],
            {
                "role": "user",
                "content": f"Available information:\n{context}\n\nQuestion: {request.message}",
            },
        ]

    @staticmethod
    def _with_citations(answer: str, sources: list[ChatSource]) -> str:
        if not sources:
            return answer
        citations: list[str] = []
        for source in sources:
            if source.source_type == "policy_fact":
                citation = f"Policy {source.policy_id}, {source.section}"
            else:
                section = source.section or "unspecified section"
                citation = f"Policy {source.policy_id}, {section}, page {source.page}"
            if citation not in citations:
                citations.append(citation)
        return f"{answer.rstrip()}\n\nSources: " + "; ".join(citations)

    async def _prepare(self, request: ChatRequest) -> tuple[Intent, str, list[ChatSource], bool]:
        intent: Intent
        if request.form_context is not None and request.form_context.field:
            intent = "field_help"
        else:
            intent = route_intent(request.message)
        context, sources, has_context = await self._context(request, intent)
        return intent, context, sources, has_context

    async def chat(self, request: ChatRequest) -> ChatResponse:
        started = time.monotonic()
        try:
            intent, context, sources, has_context = await self._prepare(request)
        except ProviderError:
            await self._audit(
                request,
                route_intent(request.message),
                "I could not retrieve policy information right now.",
                [],
                self.settings.embed_model,
                0,
                0,
                int((time.monotonic() - started) * 1000),
            )
            raise
        if intent == "handoff":
            answer = (
                OTHER_USER_MESSAGE if _is_other_user_request(request.message) else HANDOFF_MESSAGE
            )
            model = "none"
            input_tokens = output_tokens = 0
        elif not has_context:
            answer = NO_FIELD_CONTEXT if intent == "field_help" else NO_POLICY_CONTEXT
            model = "none"
            input_tokens = output_tokens = 0
        else:
            try:
                result = await self.llm.complete(
                    await _prompt(intent),
                    self._messages(request, context),
                    self.settings.llm_max_tokens,
                    self.settings.llm_temperature,
                )
            except ProviderError:
                elapsed = int((time.monotonic() - started) * 1000)
                await self._audit(
                    request,
                    intent,
                    "The language model could not complete this request.",
                    sources,
                    self.settings.llm_model,
                    0,
                    0,
                    elapsed,
                )
                raise
            answer = self._with_citations(result.text, sources)
            model = result.model
            input_tokens, output_tokens = result.input_tokens, result.output_tokens
        latency_ms = int((time.monotonic() - started) * 1000)
        await self._audit(
            request, intent, answer, sources, model, input_tokens, output_tokens, latency_ms
        )
        return ChatResponse(
            intent=intent,
            answer=answer,
            sources=sources,
            conversation_id=request.conversation_id,
            model=model,
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[str]:
        started = time.monotonic()
        try:
            intent, context, sources, has_context = await self._prepare(request)
        except ProviderError:
            await self._audit(
                request,
                route_intent(request.message),
                "I could not retrieve policy information right now.",
                [],
                self.settings.embed_model,
                0,
                0,
                int((time.monotonic() - started) * 1000),
            )
            raise
        metadata = {"intent": intent, "sources": [source.model_dump() for source in sources]}
        yield f"event: metadata\ndata: {json.dumps(metadata)}\n\n"
        if intent == "handoff":
            answer = (
                OTHER_USER_MESSAGE if _is_other_user_request(request.message) else HANDOFF_MESSAGE
            )
            model = "none"
            yield f"event: token\ndata: {json.dumps({'text': answer})}\n\n"
        elif not has_context:
            answer = NO_FIELD_CONTEXT if intent == "field_help" else NO_POLICY_CONTEXT
            model = "none"
            yield f"event: token\ndata: {json.dumps({'text': answer})}\n\n"
        else:
            response_parts: list[str] = []
            model = self.settings.llm_model
            try:
                async for token in self.llm.stream(
                    await _prompt(intent),
                    self._messages(request, context),
                    self.settings.llm_max_tokens,
                    self.settings.llm_temperature,
                ):
                    response_parts.append(token)
                    yield f"event: token\ndata: {json.dumps({'text': token})}\n\n"
            except ProviderError:
                await self._audit(
                    request,
                    intent,
                    "".join(response_parts),
                    sources,
                    model,
                    0,
                    0,
                    int((time.monotonic() - started) * 1000),
                )
                raise
            answer = self._with_citations("".join(response_parts), sources)
            if sources:
                raw_answer = "".join(response_parts)
                citation_suffix = answer[len(raw_answer) :]
                yield f"event: token\ndata: {json.dumps({'text': citation_suffix})}\n\n"
        await self._audit(
            request,
            intent,
            answer,
            sources,
            model,
            0,
            0,
            int((time.monotonic() - started) * 1000),
        )
        yield "event: done\ndata: {}\n\n"
