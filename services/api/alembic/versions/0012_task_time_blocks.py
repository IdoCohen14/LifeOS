"""Explicitly approved personal task time-block links."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"


def upgrade():
    op.create_table(
        "task_time_blocks",
        sa.Column(
            "task_id", sa.String(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "event_id",
            sa.String(),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
    )


def downgrade():
    op.drop_table("task_time_blocks")
