# Migration patterns

The full example (model + migration) was run against PostgreSQL 16 + pgvector: `upgrade`,
`downgrade -1`, `upgrade`, and `alembic check` showed no drift for the new table. Resulting names:
`pk_message_ratings`, `fk_message_ratings_message_id_messages`, `uq_message_ratings_message_id`,
`ck_message_ratings_rating_range`, index `ix_message_ratings_message_id`.

## Contents
1. Complete example: new table  2. Add / alter / rename  3. Enums  4. pgvector and special indexes
5. Partial unique index  6. Verification commands

## 1. Complete example: new table

Model `src/app/models/message_rating.py` (also add it to `models/__init__.py`):

```python
"""Message rating ORM model."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKey, schema_qualified

if TYPE_CHECKING:
    from app.models.message import Message


class MessageRating(UUIDPrimaryKey, TimestampMixin, Base):
    """A user's 1-5 rating of one assistant message."""

    __tablename__ = "message_ratings"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
        UniqueConstraint("message_id", "user_id"),
        Index("ix_message_ratings_message_id", "message_id"),
    )

    message_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{schema_qualified('messages')}.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped["Message"] = relationship()
```

Migration `migrations/versions/0006_message_ratings.py`:

```python
"""Add message ratings so users can rate assistant answers."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_message_ratings"
down_revision: str | None = "0005_message_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the message_ratings table, its constraints, and its lookup index."""
    schema = op.get_context().config.attributes["db_schema"]
    op.create_table(
        "message_ratings",
        sa.Column("message_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
        sa.ForeignKeyConstraint(
            ["message_id"],
            [f"{schema}.messages.id"],
            name="fk_message_ratings_message_id_messages",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_message_ratings"),
        sa.UniqueConstraint("message_id", "user_id", name="uq_message_ratings_message_id"),
        schema=schema,
    )
    op.create_index(
        "ix_message_ratings_message_id",
        "message_ratings",
        ["message_id"],
        schema=schema,
    )


def downgrade() -> None:
    """Drop the message_ratings table and its index."""
    schema = op.get_context().config.attributes["db_schema"]
    op.drop_index("ix_message_ratings_message_id", table_name="message_ratings", schema=schema)
    op.drop_table("message_ratings", schema=schema)
```

## 2. Add / alter / rename (from migrations 0003-0005)

```python
schema = op.get_context().config.attributes["db_schema"]

# add a nullable column, FK, and index
op.add_column("messages", sa.Column("model_id", sa.Uuid(as_uuid=True), nullable=True), schema=schema)
op.create_foreign_key(
    "fk_messages_model_id_models", "messages", "models", ["model_id"], ["id"],
    source_schema=schema, referent_schema=schema, ondelete="SET NULL",
)
op.create_index("ix_messages_model_id", "messages", ["model_id"], schema=schema)

# change a column type with an explicit cast
op.alter_column(
    "conversations", "user_id",
    existing_type=sa.Uuid(as_uuid=True), type_=sa.String(length=255),
    existing_nullable=False, schema=schema, postgresql_using="user_id::text",
)

# rename a table and its constraints
op.rename_table("embedding_model", "models", schema=schema)
op.execute(sa.text(f'ALTER TABLE "{schema}"."models" RENAME CONSTRAINT pk_embedding_model TO pk_models'))
```

For every `upgrade` step, write the mirror step in `downgrade` in reverse order. Downgrading a type
change back can fail when data no longer fits; say so in the docstring.

## 3. Enums

```python
embedding_model_type = postgresql.ENUM(
    "embedding", "conversation", name="embedding_model_type", schema=schema, create_type=False,
)
embedding_model_type.create(op.get_bind(), checkfirst=True)   # in upgrade, before the table
# ... use embedding_model_type as a column type ...
postgresql.ENUM(name="embedding_model_type", schema=schema).drop(op.get_bind(), checkfirst=True)  # downgrade, after dropping the table
```

The ORM side sets `values_callable` so Python enum *values* (not names) are stored, and passes
`schema=get_settings().db_schema`.

## 4. pgvector and special indexes (migration 0002)

```python
op.execute("CREATE EXTENSION IF NOT EXISTS vector")   # needs privileges; image must ship pgvector
sa.Column("embedding", Vector(1536), nullable=False)   # from pgvector.sqlalchemy import Vector
op.create_index(
    "idx_document_chunk_hnsw", "document_chunk", ["embedding"],
    postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"},
    postgresql_with={"m": 16, "ef_construction": 64}, schema=schema,
)
op.create_index(   # full-text (keyword half of hybrid search)
    "idx_document_chunk_fts", "document_chunk", [sa.text("to_tsvector('english', chunk_text)")],
    postgresql_using="gin", schema=schema,
)
```

Retrieval queries must use the same operator class (`<=>` for cosine) for the HNSW index to be used.

## 5. Partial unique index ("one active row per type")

```python
op.create_index(
    "uq_single_active_model_per_type", "models", ["type"], unique=True,
    postgresql_where=sa.text("is_active = TRUE"), schema=schema,
)
```

## 6. Verification commands

```
uv run alembic heads                 # exactly one head
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
uv run alembic check                 # only the 3 known index renames (known-issues E1)
uv run ruff check . && uv run ruff format --check . && uv run mypy
```
