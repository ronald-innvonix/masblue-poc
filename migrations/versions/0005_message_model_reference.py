"""Track the registry model used to generate assistant messages."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_message_model"
down_revision: str | None = "0004_models_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add an optional model registry reference to chat messages."""
    schema = op.get_context().config.attributes["db_schema"]
    op.add_column(
        "messages",
        sa.Column("model_id", sa.Uuid(as_uuid=True), nullable=True),
        schema=schema,
    )
    op.create_foreign_key(
        "fk_messages_model_id_models",
        "messages",
        "models",
        ["model_id"],
        ["id"],
        source_schema=schema,
        referent_schema=schema,
        ondelete="SET NULL",
    )
    op.create_index("ix_messages_model_id", "messages", ["model_id"], schema=schema)


def downgrade() -> None:
    """Remove the model registry reference from chat messages."""
    schema = op.get_context().config.attributes["db_schema"]
    op.drop_index("ix_messages_model_id", table_name="messages", schema=schema)
    op.drop_constraint("fk_messages_model_id_models", "messages", schema=schema, type_="foreignkey")
    op.drop_column("messages", "model_id", schema=schema)
