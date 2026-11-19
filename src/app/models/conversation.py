"""Conversation ORM model."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.message import Message


class Conversation(UUIDPrimaryKey, TimestampMixin, Base):
    """A chat conversation owned by a user of the existing application."""

    __tablename__ = "conversations"

    # TODO(phase-2): Match this UUID column to the existing application's user ID type.
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
