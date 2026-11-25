"""Document vectorization status tracking ORM model."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKey, schema_qualified

if TYPE_CHECKING:
    from app.models.embedding_model import EmbeddingModel


class DocumentVectorStatus(UUIDPrimaryKey, Base):
    """Track lazy vectorization status per source document and embedding model."""

    __tablename__ = "document_vector_status"
    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "source_id",
            "embedding_model_id",
            name="uq_source_model_status",
        ),
    )

    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    embedding_model_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{schema_qualified('embedding_model')}.id"),
        nullable=False,
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    chunk_count: Mapped[int] = mapped_column(
        Integer,
        server_default=text("0"),
        default=0,
        nullable=False,
    )
    vectorized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    embedding_model: Mapped["EmbeddingModel"] = relationship(
        back_populates="vector_statuses",
    )
