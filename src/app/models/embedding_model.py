"""Embedding model registry ORM model."""

from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.models.base import Base, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.document_chunk import DocumentChunk
    from app.models.document_vector_status import DocumentVectorStatus


class EmbeddingModelType(str, PyEnum):
    """Purpose of a registered embedding model configuration."""

    EMBEDDING = "embedding"
    CONVERSATION = "conversation"


class EmbeddingModel(UUIDPrimaryKey, Base):
    """Registered embedding model configuration with single-active constraint."""

    __tablename__ = "embedding_model"
    __table_args__ = (
        Index(
            "uq_single_active_model",
            "is_active",
            unique=True,
            postgresql_where=text("is_active = TRUE"),
        ),
    )

    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    type: Mapped[EmbeddingModelType] = mapped_column(
        Enum(
            EmbeddingModelType,
            name="embedding_model_type",
            schema=get_settings().db_schema,
            values_callable=lambda enum_values: [value.value for value in enum_values],
        ),
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_metric: Mapped[str] = mapped_column(
        String(20),
        server_default=text("'cosine'"),
        default="cosine",
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("FALSE"),
        default=False,
        nullable=False,
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    vector_statuses: Mapped[list["DocumentVectorStatus"]] = relationship(
        back_populates="embedding_model",
    )
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="embedding_model",
    )
