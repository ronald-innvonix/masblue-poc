"""Add pgvector RAG tables and message citation/intent columns."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0002_rag_tables"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Enable pgvector and create RAG/vectorization tables in the service schema."""
    schema = op.get_context().config.attributes["db_schema"]

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column(
        "messages",
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema=schema,
    )
    op.add_column(
        "messages",
        sa.Column("intent", sa.String(length=50), nullable=True),
        schema=schema,
    )

    embedding_model_type = postgresql.ENUM(
        "embedding",
        "conversation",
        name="embedding_model_type",
        schema=schema,
        create_type=False,
    )
    embedding_model_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "embedding_model",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("type", embedding_model_type, nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column(
            "distance_metric",
            sa.String(length=20),
            server_default=sa.text("'cosine'"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("FALSE"),
            nullable=False,
        ),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_embedding_model"),
        schema=schema,
    )
    op.create_index(
        "uq_single_active_model",
        "embedding_model",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active = TRUE"),
        schema=schema,
    )

    op.create_table(
        "manual_document",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("flow_key", sa.String(length=100), nullable=False),
        sa.Column("product_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("module_content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "version",
            sa.String(length=20),
            server_default=sa.text("'1.0'"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'published'"),
            nullable=False,
        ),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_manual_document"),
        sa.UniqueConstraint("flow_key", name="uq_manual_document_flow_key"),
        schema=schema,
    )

    op.create_table(
        "document_vector_status",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("embedding_model_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "chunk_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("vectorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["embedding_model_id"],
            [f"{schema}.embedding_model.id"],
            name="fk_document_vector_status_embedding_model_id_embedding_model",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_vector_status"),
        sa.UniqueConstraint(
            "source_type",
            "source_id",
            "embedding_model_id",
            name="uq_source_model_status",
        ),
        schema=schema,
    )

    op.create_table(
        "document_chunk",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("embedding_model_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("policy_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("section_ref", sa.String(length=150), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["embedding_model_id"],
            [f"{schema}.embedding_model.id"],
            name="fk_document_chunk_embedding_model_id_embedding_model",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_chunk"),
        schema=schema,
    )
    op.create_index(
        "idx_document_chunk_hnsw",
        "document_chunk",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_with={"m": 16, "ef_construction": 64},
        schema=schema,
    )
    op.create_index(
        "idx_document_chunk_tenant_filter",
        "document_chunk",
        ["embedding_model_id", "tenant_id", "policy_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_document_chunk_fts",
        "document_chunk",
        [sa.text("to_tsvector('english', chunk_text)")],
        unique=False,
        postgresql_using="gin",
        schema=schema,
    )


def downgrade() -> None:
    """Drop RAG/vectorization tables and message citation/intent columns."""
    schema = op.get_context().config.attributes["db_schema"]

    op.drop_index("idx_document_chunk_fts", table_name="document_chunk", schema=schema)
    op.drop_index("idx_document_chunk_tenant_filter", table_name="document_chunk", schema=schema)
    op.drop_index("idx_document_chunk_hnsw", table_name="document_chunk", schema=schema)
    op.drop_table("document_chunk", schema=schema)

    op.drop_table("document_vector_status", schema=schema)
    op.drop_table("manual_document", schema=schema)

    op.drop_index("uq_single_active_model", table_name="embedding_model", schema=schema)
    op.drop_table("embedding_model", schema=schema)
    postgresql.ENUM(name="embedding_model_type", schema=schema).drop(
        op.get_bind(),
        checkfirst=True,
    )

    op.drop_column("messages", "intent", schema=schema)
    op.drop_column("messages", "citations", schema=schema)
