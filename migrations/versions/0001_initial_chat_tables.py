"""Create the initial conversations and messages tables in the service schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create service-owned chat tables and indexes."""
    schema = op.get_context().config.attributes["db_schema"]
    op.create_table(
        "conversations",
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
        schema=schema,
    )
    op.create_index(
        "ix_conversations_user_id",
        "conversations",
        ["user_id"],
        schema=schema,
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("conversation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="ck_messages_message_role",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            [f"{schema}.conversations.id"],
            name="fk_messages_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
        schema=schema,
    )
    op.create_index(
        "ix_messages_conversation_id",
        "messages",
        ["conversation_id"],
        schema=schema,
    )


def downgrade() -> None:
    """Drop only the two service-owned tables and their indexes."""
    schema = op.get_context().config.attributes["db_schema"]
    op.drop_index("ix_messages_conversation_id", table_name="messages", schema=schema)
    op.drop_table("messages", schema=schema)
    op.drop_index("ix_conversations_user_id", table_name="conversations", schema=schema)
    op.drop_table("conversations", schema=schema)
