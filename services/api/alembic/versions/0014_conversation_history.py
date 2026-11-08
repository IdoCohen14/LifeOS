"""Opt-in text-only local assistant history, separate from operational proposals."""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"


def upgrade():
    op.create_table(
        "assistant_history_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
    )
    op.create_table(
        "assistant_conversation_turns",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("turn_id", sa.String(36), nullable=False, unique=True),
        sa.Column("user_text", sa.String(1500), nullable=False),
        sa.Column("assistant_text", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index(
        "ix_assistant_conversation_turns_created_at", "assistant_conversation_turns", ["created_at"]
    )


def downgrade():
    op.drop_table("assistant_conversation_turns")
    op.drop_table("assistant_history_preferences")
