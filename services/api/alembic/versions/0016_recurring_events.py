"""Separate finite weekly event approval; no assistant action replay."""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"


def upgrade():
    op.create_table(
        "recurrence_proposals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "session_hash",
            sa.String(),
            sa.ForeignKey("sessions.token_hash", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("payload", sa.String(), nullable=False),
        sa.Column("expires", sa.Integer(), nullable=False),
        sa.Column("event_ids", sa.String(), nullable=True),
        sa.Column("confirmed_at", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_recurrence_proposals_session_hash", "recurrence_proposals", ["session_hash"]
    )
    op.create_index("ix_recurrence_proposals_expires", "recurrence_proposals", ["expires"])


def downgrade():
    op.drop_table("recurrence_proposals")
