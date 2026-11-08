"""Opt-in operational briefing schedules and numeric snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"


def upgrade():
    op.add_column(
        "notification_preferences",
        sa.Column("briefings", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "briefing_schedule",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("daily_enabled", sa.Boolean(), nullable=False),
        sa.Column("daily_time", sa.String(5), nullable=False),
        sa.Column("weekly_enabled", sa.Boolean(), nullable=False),
        sa.Column("weekly_day", sa.Integer(), nullable=False),
        sa.Column("weekly_time", sa.String(5), nullable=False),
        sa.Column("last_run", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
    )
    op.create_table(
        "scheduled_briefings",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("period_start", sa.String(10), nullable=False),
        sa.Column("timezone", sa.String(), nullable=False),
        sa.Column("generated_at", sa.String(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_index("ix_scheduled_briefings_period_start", "scheduled_briefings", ["period_start"])
    op.create_index("ix_scheduled_briefings_generated_at", "scheduled_briefings", ["generated_at"])


def downgrade():
    op.drop_table("scheduled_briefings")
    op.drop_table("briefing_schedule")
    with op.batch_alter_table("notification_preferences") as batch:
        batch.drop_column("briefings")
