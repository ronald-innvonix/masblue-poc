import re
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatAudit, FieldGlossary, PolicyChunk, PolicyDocument, PolicyFact


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_glossary(self, query: str) -> list[FieldGlossary]:
        ignored_terms = {"what", "does", "the", "mean", "field", "form", "help", "explain"}
        terms = [
            term
            for term in re.findall(r"[a-z0-9_]+", query.lower())
            if len(term) > 2 and term not in ignored_terms
        ]
        if not terms:
            return []
        statement = select(FieldGlossary)
        statement = statement.where(
            or_(
                *(
                    FieldGlossary.field_key.ilike(f"%{term}%")
                    | FieldGlossary.label.ilike(f"%{term}%")
                    for term in terms[:6]
                )
            )
        )
        return list((await self.session.scalars(statement.limit(5))).all())

    async def get_glossary_field(self, field_key: str) -> FieldGlossary | None:
        return await self.session.scalar(
            select(FieldGlossary).where(FieldGlossary.field_key == field_key)
        )

    async def policy_facts(
        self, user_id: str, policy_ids: Sequence[str] | None = None
    ) -> list[PolicyFact]:
        statement = select(PolicyFact).where(PolicyFact.user_id == user_id)
        if policy_ids:
            statement = statement.where(PolicyFact.policy_id.in_(policy_ids))
        return list((await self.session.scalars(statement)).all())

    async def retrieve_chunks(
        self,
        user_id: str,
        policy_ids: Sequence[str] | None,
        embedding: list[float],
        limit: int,
    ) -> list[tuple[PolicyChunk, float]]:
        distance = PolicyChunk.embedding.cosine_distance(embedding)
        statement = (
            select(PolicyChunk, distance.label("distance"))
            .join(PolicyDocument, PolicyChunk.document_id == PolicyDocument.id)
            .where(
                PolicyChunk.user_id == user_id,
                PolicyDocument.user_id == user_id,
                PolicyDocument.status == "ready",
            )
            .order_by(distance)
            .limit(limit)
        )
        if policy_ids:
            statement = statement.where(PolicyChunk.policy_id.in_(policy_ids))
        rows = (await self.session.execute(statement)).all()
        return [(row[0], float(row[1])) for row in rows]

    async def create_or_replace_document(
        self, user_id: str, policy_id: str, filename: str, digest: str
    ) -> PolicyDocument | None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"{user_id}:{policy_id}:{filename}"},
        )
        statement = select(PolicyDocument).where(
            PolicyDocument.user_id == user_id,
            PolicyDocument.policy_id == policy_id,
            PolicyDocument.filename == filename,
        )
        document = await self.session.scalar(statement)
        if document is None:
            return None
        if document.content_sha256 != digest:
            return None
        await self.session.execute(
            delete(PolicyChunk).where(PolicyChunk.document_id == document.id)
        )
        document.status = "processing"
        document.error_message = None
        return document

    async def queue_document(
        self, user_id: str, policy_id: str, filename: str, digest: str
    ) -> PolicyDocument:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"{user_id}:{policy_id}:{filename}"},
        )
        statement = select(PolicyDocument).where(
            PolicyDocument.user_id == user_id,
            PolicyDocument.policy_id == policy_id,
            PolicyDocument.filename == filename,
        )
        document = await self.session.scalar(statement)
        if document is None:
            document = PolicyDocument(
                user_id=user_id,
                policy_id=policy_id,
                filename=filename,
                content_sha256=digest,
                status="queued",
            )
            self.session.add(document)
        else:
            document.content_sha256 = digest
            document.status = "queued"
            document.error_message = None
        await self.session.flush()
        return document

    async def insert_document(
        self, user_id: str, policy_id: str, filename: str, digest: str
    ) -> PolicyDocument:
        document = PolicyDocument(
            user_id=user_id, policy_id=policy_id, filename=filename, content_sha256=digest
        )
        self.session.add(document)
        await self.session.flush()
        return document

    async def add_chunks(
        self,
        document: PolicyDocument,
        contents: list[tuple[str, str | None, int]],
        embeddings: list[list[float]],
    ) -> None:
        self.session.add_all(
            [
                PolicyChunk(
                    document_id=document.id,
                    user_id=document.user_id,
                    policy_id=document.policy_id,
                    chunk_index=index,
                    content=content,
                    section=section,
                    page_number=page_number,
                    embedding=embedding,
                )
                for index, ((content, section, page_number), embedding) in enumerate(
                    zip(contents, embeddings, strict=True)
                )
            ]
        )

    async def add_audit(
        self,
        user_id: str,
        policy_id: str | None,
        intent: str,
        question: str,
        answer: str,
        sources: list[dict[str, object]],
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
    ) -> None:
        self.session.add(
            ChatAudit(
                user_id=user_id,
                policy_id=policy_id,
                intent=intent,
                question=question,
                answer=answer,
                sources=sources,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
            )
        )
        await self.session.commit()

    async def document_status(self, document_id: str, user_id: str) -> PolicyDocument | None:
        return await self.session.scalar(
            select(PolicyDocument).where(
                PolicyDocument.id == document_id, PolicyDocument.user_id == user_id
            )
        )

    async def set_document_status(
        self, document: PolicyDocument, status: str, error_message: str | None = None
    ) -> None:
        document.status = status
        document.error_message = error_message
        await self.session.flush()

    async def vector_dimension(self) -> int | None:
        result: Any = await self.session.execute(
            text(
                "SELECT atttypmod FROM pg_attribute "
                "WHERE attrelid = 'policy_chunks'::regclass AND attname = 'embedding'"
            )
        )
        typmod = result.scalar_one_or_none()
        return int(typmod) if typmod is not None and typmod > 0 else None

    async def ping(self) -> None:
        await self.session.execute(text("SELECT 1"))

    async def upsert_glossary(self, field_key: str, label: str, definition: str) -> None:
        statement = insert(FieldGlossary).values(
            field_key=field_key, label=label, definition=definition
        )
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["field_key"],
                set_={"label": label, "definition": definition},
            )
        )
