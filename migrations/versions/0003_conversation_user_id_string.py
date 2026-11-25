"""Store the upstream JWT subject without assuming it is a UUID."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_user_id_string"
down_revision: str | None = "0002_rag_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Convert conversation owners to strings to match JWT subject values."""
    schema = op.get_context().config.attributes["db_schema"]
    op.alter_column(
        "conversations",
        "user_id",
        existing_type=sa.Uuid(as_uuid=True),
        type_=sa.String(length=255),
        existing_nullable=False,
        schema=schema,
        postgresql_using="user_id::text",
    )


def downgrade() -> None:
    """Convert conversation owners back to UUIDs where stored values permit it."""
    schema = op.get_context().config.attributes["db_schema"]
    op.alter_column(
        "conversations",
        "user_id",
        existing_type=sa.String(length=255),
        type_=sa.Uuid(as_uuid=True),
        existing_nullable=False,
        schema=schema,
        postgresql_using="user_id::uuid",
    )
