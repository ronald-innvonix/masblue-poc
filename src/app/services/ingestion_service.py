import asyncio
import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePath
from uuid import UUID

import pymupdf
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidDocumentError, ProviderError
from app.db.repositories.chat_repository import ChatRepository
from app.llm.base import EmbeddingProvider

CHUNK_SIZE = 1_000
CHUNK_OVERLAP = 150
_HEADING = re.compile(r"^(?:SECTION\s+\d+[\w.-]*|[A-Z][A-Z0-9 &/(),:'-]{2,})$")


@dataclass(frozen=True)
class PdfChunk:
    content: str
    section: str | None
    page_number: int


def extract_pdf_pages(data: bytes) -> list[tuple[int, str]]:
    try:
        with pymupdf.open(stream=data, filetype="pdf") as document:  # type: ignore[no-untyped-call]
            pages = [(page.number + 1, page.get_text("text")) for page in document]
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise InvalidDocumentError("Uploaded file is not a readable PDF") from exc
    if not pages or not any(text.strip() for _, text in pages):
        raise InvalidDocumentError(
            "PDF contains no extractable text; scanned or image-only PDFs are not supported"
        )
    return pages


def extract_pdf_text(data: bytes) -> str:
    return "\n".join(text for _, text in extract_pdf_pages(data))


def _chunk_section(text: str, section: str | None, page_number: int) -> list[PdfChunk]:
    normalized = re.sub(r"[ \t]+", " ", text).strip()
    if not normalized:
        return []
    chunks: list[PdfChunk] = []
    start = 0
    while start < len(normalized):
        end = min(start + CHUNK_SIZE, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind(" ", start, end)
            if boundary > start:
                end = boundary
        content = normalized[start:end].strip()
        if content:
            chunks.append(PdfChunk(content, section, page_number))
        if end >= len(normalized):
            break
        start = max(start + 1, end - CHUNK_OVERLAP)
    return chunks


def _is_heading(line: str) -> bool:
    if len(line) > 100:
        return False
    return bool(
        re.fullmatch(r"SECTION\s+\d+[\w.-]*", line, re.IGNORECASE)
        or (_HEADING.fullmatch(line) and line.isupper())
        or (line.istitle() and not line.endswith((".", "!", "?")))
    )


def chunk_pdf_pages(pages: list[tuple[int, str]]) -> list[PdfChunk]:
    chunks: list[PdfChunk] = []
    current_section: str | None = None
    for page_number, page_text in pages:
        section_lines: list[str] = []
        section_for_content = current_section
        for raw_line in page_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if _is_heading(line):
                chunks.extend(
                    _chunk_section("\n".join(section_lines), section_for_content, page_number)
                )
                section_lines = []
                current_section = line
                section_for_content = line
            else:
                section_lines.append(line)
        chunks.extend(_chunk_section("\n".join(section_lines), section_for_content, page_number))
    return chunks


class IngestionService:
    def __init__(self, session: AsyncSession, embeddings: EmbeddingProvider) -> None:
        self.session = session
        self.repository = ChatRepository(session)
        self.embeddings = embeddings

    @staticmethod
    def _validate_filename(filename: str) -> None:
        if not filename or len(filename) > 255 or PurePath(filename).suffix.lower() != ".pdf":
            raise InvalidDocumentError("Only PDF documents are supported")

    async def enqueue(self, user_id: str, policy_id: str, filename: str, data: bytes) -> UUID:
        if not user_id or len(user_id) > 128 or not policy_id or len(policy_id) > 128:
            raise InvalidDocumentError("User and policy identifiers must be 1 to 128 characters")
        self._validate_filename(filename)
        digest = hashlib.sha256(data).hexdigest()
        document = await self.repository.queue_document(user_id, policy_id, filename, digest)
        await self.session.commit()
        return document.id

    async def process_queued(self, document_id: UUID, user_id: str, data: bytes) -> int:
        document = await self.repository.document_status(str(document_id), user_id)
        if document is None:
            raise InvalidDocumentError("Queued policy document could not be found")
        digest = hashlib.sha256(data).hexdigest()
        if document.content_sha256 != digest:
            return 0
        await self.repository.set_document_status(document, "processing")
        await self.session.commit()
        try:
            self._validate_filename(document.filename)
            pages = await asyncio.to_thread(extract_pdf_pages, data)
            chunks = await asyncio.to_thread(chunk_pdf_pages, pages)
            if not chunks:
                raise InvalidDocumentError("PDF contains no extractable text")
            vectors = await self.embeddings.embed([chunk.content for chunk in chunks])
            if (
                len(vectors) != len(chunks)
                or not vectors
                or any(not vector or len(vector) != len(vectors[0]) for vector in vectors)
            ):
                raise InvalidDocumentError(
                    "Embedding provider returned inconsistent vector dimensions"
                )
            dimension = await self.repository.vector_dimension()
            if dimension is None or len(vectors[0]) != dimension:
                raise InvalidDocumentError(
                    "Embedding provider dimension does not match policy_chunks.embedding"
                )
            updated_document = await self.repository.create_or_replace_document(
                user_id,
                document.policy_id,
                document.filename,
                digest,
            )
            if updated_document is None:
                await self.session.rollback()
                return 0
            chunk_values = [(chunk.content, chunk.section, chunk.page_number) for chunk in chunks]
            await self.repository.add_chunks(updated_document, chunk_values, vectors)
            await self.repository.set_document_status(updated_document, "ready")
            await self.session.commit()
        except InvalidDocumentError as exc:
            await self.session.rollback()
            failed_document = await self.repository.document_status(str(document_id), user_id)
            if failed_document is not None and failed_document.content_sha256 == digest:
                await self.repository.set_document_status(failed_document, "failed", exc.message)
                await self.session.commit()
            raise
        except ProviderError:
            await self.session.rollback()
            failed_document = await self.repository.document_status(str(document_id), user_id)
            if failed_document is not None and failed_document.content_sha256 == digest:
                await self.repository.set_document_status(
                    failed_document, "failed", "Embedding provider failed"
                )
                await self.session.commit()
            raise
        return len(chunks)

    async def ingest(
        self, user_id: str, policy_id: str, filename: str, data: bytes
    ) -> tuple[UUID, int]:
        document_id = await self.enqueue(user_id, policy_id, filename, data)
        count = await self.process_queued(document_id, user_id, data)
        return document_id, count
