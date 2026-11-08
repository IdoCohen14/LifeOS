"""Session-owned reviewed weekly clock changes; existing events unchanged."""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"


def upgrade():
    op.create_table(
        "series_reschedule_proposals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "session_hash",
            sa.String(),
            sa.ForeignKey("sessions.token_hash", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("payload", sa.String(), nullable=False),
        sa.Column("expires", sa.Integer(), nullable=False),
        sa.Column("changed_count", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_series_reschedule_proposals_session_hash",
        "series_reschedule_proposals",
        ["session_hash"],
    )
    op.create_index(
        "ix_series_reschedule_proposals_expires", "series_reschedule_proposals", ["expires"]
    )


def downgrade():
    op.drop_table("series_reschedule_proposals")
