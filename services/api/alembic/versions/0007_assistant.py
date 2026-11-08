"""Session-bound, expiring assistant proposals with idempotent confirmation."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"


def upgrade():
    op.create_table(
        "assistant_proposals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "session_hash",
            sa.String(),
            sa.ForeignKey("sessions.token_hash", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("payload", sa.String(), nullable=False),
        sa.Column("expires", sa.Integer(), nullable=False),
        sa.Column("confirmed_id", sa.String(), nullable=True),
    )
    op.create_index("ix_assistant_proposals_session_hash", "assistant_proposals", ["session_hash"])


def downgrade():
    op.drop_table("assistant_proposals")
