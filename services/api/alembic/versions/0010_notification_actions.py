"""Versioned notification dismissal and elapsed-time snooze."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"


def upgrade():
    op.create_table(
        "notification_actions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("dismissed", sa.Boolean(), nullable=False),
        sa.Column("snoozed_until", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_notification_actions_updated_at", "notification_actions", ["updated_at"])


def downgrade():
    op.drop_table("notification_actions")
