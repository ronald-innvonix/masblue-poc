"""Document chunk and pgvector store ORM model."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKey, schema_qualified

if TYPE_CHECKING:
    from app.models.embedding_model import EmbeddingModel


class DocumentChunk(UUIDPrimaryKey, Base):
    """Chunked document text and vector embedding for hybrid pgvector + BM25 search."""

    __tablename__ = "document_chunk"
    __table_args__ = (
        Index(
            "idx_document_chunk_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
        ),
        Index(
            "idx_document_chunk_tenant_filter",
            "embedding_model_id",
            "tenant_id",
            "policy_id",
        ),
        Index(
            "idx_document_chunk_fts",
            text("to_tsvector('english', chunk_text)"),
            postgresql_using="gin",
        ),
    )

    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    embedding_model_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{schema_qualified('embedding_model')}.id"),
        nullable=False,
    )
    tenant_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    policy_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    section_ref: Mapped[str | None] = mapped_column(String(150), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        server_default=text("'{}'::jsonb"),
        default=dict,
        nullable=False,
    )
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    embedding_model: Mapped["EmbeddingModel"] = relationship(
        back_populates="chunks",
    )
