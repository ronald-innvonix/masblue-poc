"""Extend chat audits and ingestion metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0002_chat_audit_ingestion_metadata"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "policy_documents",
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.alter_column("policy_documents", "status", server_default="queued")
    op.add_column("policy_chunks", sa.Column("section", sa.String(255), nullable=True))
    op.add_column(
        "policy_chunks",
        sa.Column("page_number", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("chat_audit", sa.Column("policy_id", sa.String(128), nullable=True))
    op.add_column(
        "chat_audit",
        sa.Column("question", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "chat_audit",
        sa.Column("answer", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "chat_audit",
        sa.Column(
            "sources",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )


def downgrade() -> None:
    op.drop_column("chat_audit", "sources")
    op.drop_column("chat_audit", "answer")
    op.drop_column("chat_audit", "question")
    op.drop_column("chat_audit", "policy_id")
    op.drop_column("policy_chunks", "page_number")
    op.drop_column("policy_chunks", "section")
    op.drop_column("policy_documents", "error_message")
    op.alter_column("policy_documents", "status", server_default="ready")
