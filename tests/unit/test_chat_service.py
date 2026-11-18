from collections.abc import Sequence
from types import SimpleNamespace

import pytest
from tests.fakes import FakeEmbeddingProvider, FakeLLMProvider

from app.db.models import ChatAudit, FieldGlossary
from app.schemas.chat import ChatRequest, FormContext
from app.services.chat_service import NO_POLICY_CONTEXT, OTHER_USER_MESSAGE, ChatService
from app.services.retrieval_service import RetrievedChunk


class EmptyResult:
    def all(self) -> list[object]:
        return []


class FakeSession:
    def __init__(self, glossary: FieldGlossary | None = None) -> None:
        self.added: list[object] = []
        self.glossary = glossary

    def add(self, item: object) -> None:
        self.added.append(item)

    async def commit(self) -> None:
        return None

    async def execute(self, statement: object) -> EmptyResult:
        return EmptyResult()

    async def scalars(self, statement: object) -> EmptyResult:
        return EmptyResult()

    async def scalar(self, statement: object) -> FieldGlossary | None:
        return self.glossary


class FakeRetrieval:
    def __init__(self, chunks: Sequence[RetrievedChunk]) -> None:
        self.chunks = list(chunks)

    async def retrieve(
        self, user_id: str, policy_ids: list[str] | None, query: str
    ) -> list[RetrievedChunk]:
        return self.chunks


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        llm_model="test-model",
        llm_max_tokens=100,
        llm_temperature=0.0,
        retrieval_min_score=0.25,
    )


@pytest.mark.asyncio
async def test_fake_embedding_provider_is_deterministic_shape() -> None:
    vectors = await FakeEmbeddingProvider().embed(["policy text"])

    assert len(vectors) == 1
    assert len(vectors[0]) == 384


@pytest.mark.asyncio
async def test_empty_policy_context_returns_fixed_answer_without_llm() -> None:
    llm = FakeLLMProvider()
    session = FakeSession()
    service = ChatService(
        session,
        llm,
        FakeRetrieval([]),
        _settings(),  # type: ignore[arg-type]
    )
    answer = await service.chat(ChatRequest(user_id="user-a", message="Is water damage covered?"))

    assert answer.answer == NO_POLICY_CONTEXT
    assert llm.calls == 0
    assert len(session.added) == 1


@pytest.mark.asyncio
async def test_other_users_policy_request_is_refused_without_llm() -> None:
    llm = FakeLLMProvider()
    session = FakeSession()
    service = ChatService(
        session,
        llm,
        FakeRetrieval([]),
        _settings(),  # type: ignore[arg-type]
    )
    answer = await service.chat(
        ChatRequest(
            user_id="user-a",
            message="Can you tell me about my neighbor's policy?",
        )
    )

    assert answer.answer == OTHER_USER_MESSAGE
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_policy_answer_has_source_citations_and_audit() -> None:
    llm = FakeLLMProvider()
    session = FakeSession()
    chunk = RetrievedChunk(
        policy_id="POL-1",
        document_id="doc-1",
        chunk_index=0,
        content="Water damage is subject to the exclusion.",
        section="Exclusions",
        page_number=3,
        score=0.9,
    )
    service = ChatService(
        session,
        llm,
        FakeRetrieval([chunk]),
        _settings(),  # type: ignore[arg-type]
    )
    answer = await service.chat(
        ChatRequest(user_id="user-a", policy_id="POL-1", message="Is water damage covered?")
    )

    assert "Sources: Policy POL-1, Exclusions, page 3" in answer.answer
    assert answer.sources[0].page == 3
    assert llm.calls == 1
    audit = session.added[0]
    assert isinstance(audit, ChatAudit)
    assert audit.question == "Is water damage covered?"
    assert audit.sources[0]["policy_id"] == "POL-1"


@pytest.mark.asyncio
async def test_streaming_chat_includes_citations_and_writes_audit() -> None:
    llm = FakeLLMProvider()
    session = FakeSession()
    chunk = RetrievedChunk(
        policy_id="POL-1",
        document_id="doc-1",
        chunk_index=0,
        content="Water damage is subject to the exclusion.",
        section="Exclusions",
        page_number=3,
        score=0.9,
    )
    service = ChatService(
        session,
        llm,
        FakeRetrieval([chunk]),
        _settings(),  # type: ignore[arg-type]
    )
    events = [
        event
        async for event in service.stream(
            ChatRequest(user_id="user-a", message="Is water damage covered?")
        )
    ]

    assert any("Sources: Policy POL-1, Exclusions, page 3" in event for event in events)
    assert events[-1] == "event: done\ndata: {}\n\n"
    assert len(session.added) == 1


@pytest.mark.asyncio
async def test_form_context_uses_exact_glossary_field_and_includes_history() -> None:
    llm = FakeLLMProvider()
    session = FakeSession(
        FieldGlossary(
            field_key="deductible",
            label="Deductible",
            definition="The amount paid before covered benefits apply.",
        )
    )
    service = ChatService(
        session,
        llm,
        FakeRetrieval([]),
        _settings(),  # type: ignore[arg-type]
    )
    answer = await service.chat(
        ChatRequest(
            user_id="user-a",
            message="Can you explain this?",
            form_context=FormContext(form="home", field="Deductible"),
            history=[{"role": "user", "content": "I am filling out the form."}],
        )
    )

    assert answer.intent == "field_help"
    assert llm.calls == 1
    assert "I am filling out the form." in llm.last_messages[0]["content"]
