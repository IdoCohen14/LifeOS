"""Optional per-account actual conversation text, never executable proposals."""

import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"


def upgrade():
    op.create_table(
        "account_conversation_turns",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("account_id", sa.String(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("user_text", sa.Text(), nullable=False),
        sa.Column("reply_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("include_context", sa.Boolean(), nullable=False),
    )
    op.create_index(
        "ix_account_conversation_turns_account_id", "account_conversation_turns", ["account_id"]
    )
    op.create_index(
        "ix_account_conversation_turns_created_at", "account_conversation_turns", ["created_at"]
    )


def downgrade():
    op.drop_table("account_conversation_turns")
