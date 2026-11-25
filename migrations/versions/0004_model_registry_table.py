"""Rename the model registry table and add provider connection fields."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_models_table"
down_revision: str | None = "0003_user_id_string"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename the registry, allow nullable metadata, and add API connection fields."""
    schema = op.get_context().config.attributes["db_schema"]

    op.drop_index("uq_single_active_model", table_name="embedding_model", schema=schema)
    op.rename_table("embedding_model", "models", schema=schema)
    op.execute(
        sa.text(
            f'ALTER TABLE "{schema}"."models" RENAME CONSTRAINT pk_embedding_model TO pk_models'
        )
    )
    op.execute(
        sa.text(
            f'ALTER TABLE "{schema}"."document_vector_status" '
            "RENAME CONSTRAINT "
            "fk_document_vector_status_embedding_model_id_embedding_model "
            "TO fk_document_vector_status_embedding_model_id_models"
        )
    )
    op.execute(
        sa.text(
            f'ALTER TABLE "{schema}"."document_chunk" '
            "RENAME CONSTRAINT "
            "fk_document_chunk_embedding_model_id_embedding_model "
            "TO fk_document_chunk_embedding_model_id_models"
        )
    )

    op.alter_column("models", "provider", existing_type=sa.String(50), nullable=True, schema=schema)
    op.alter_column(
        "models",
        "type",
        existing_type=sa.Enum(name="embedding_model_type", schema=schema),
        nullable=True,
        schema=schema,
    )
    op.alter_column(
        "models",
        "model_name",
        existing_type=sa.String(100),
        new_column_name="model",
        nullable=True,
        schema=schema,
    )
    op.alter_column(
        "models", "dimensions", existing_type=sa.Integer(), nullable=True, schema=schema
    )
    op.alter_column(
        "models",
        "distance_metric",
        existing_type=sa.String(20),
        nullable=True,
        schema=schema,
    )
    op.alter_column(
        "models",
        "activated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        schema=schema,
    )
    op.add_column(
        "models", sa.Column("api_key", sa.String(length=512), nullable=True), schema=schema
    )
    op.add_column(
        "models", sa.Column("base_url", sa.String(length=2048), nullable=True), schema=schema
    )
    op.create_index(
        "uq_single_active_model_per_type",
        "models",
        ["type"],
        unique=True,
        postgresql_where=sa.text("is_active = TRUE"),
        schema=schema,
    )


def downgrade() -> None:
    """Restore the original embedding model registry shape."""
    schema = op.get_context().config.attributes["db_schema"]

    op.drop_index("uq_single_active_model_per_type", table_name="models", schema=schema)
    op.drop_column("models", "base_url", schema=schema)
    op.drop_column("models", "api_key", schema=schema)
    op.alter_column(
        "models",
        "activated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        schema=schema,
    )
    op.alter_column(
        "models", "distance_metric", existing_type=sa.String(20), nullable=False, schema=schema
    )
    op.alter_column(
        "models", "dimensions", existing_type=sa.Integer(), nullable=False, schema=schema
    )
    op.alter_column(
        "models",
        "model",
        existing_type=sa.String(100),
        new_column_name="model_name",
        nullable=False,
        schema=schema,
    )
    op.alter_column(
        "models",
        "type",
        existing_type=sa.Enum(name="embedding_model_type", schema=schema),
        nullable=False,
        schema=schema,
    )
    op.alter_column(
        "models", "provider", existing_type=sa.String(50), nullable=False, schema=schema
    )
    op.execute(
        sa.text(
            f'ALTER TABLE "{schema}"."models" RENAME CONSTRAINT pk_models TO pk_embedding_model'
        )
    )
    op.execute(
        sa.text(
            f'ALTER TABLE "{schema}"."document_vector_status" '
            "RENAME CONSTRAINT fk_document_vector_status_embedding_model_id_models "
            "TO fk_document_vector_status_embedding_model_id_embedding_model"
        )
    )
    op.execute(
        sa.text(
            f'ALTER TABLE "{schema}"."document_chunk" '
            "RENAME CONSTRAINT fk_document_chunk_embedding_model_id_models "
            "TO fk_document_chunk_embedding_model_id_embedding_model"
        )
    )
    op.rename_table("models", "embedding_model", schema=schema)
    op.create_index(
        "uq_single_active_model",
        "embedding_model",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active = TRUE"),
        schema=schema,
    )
