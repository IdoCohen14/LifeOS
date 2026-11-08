"""In-app notification preferences and versioned read acknowledgements."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"


def upgrade():
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("tasks", sa.Boolean(), nullable=False),
        sa.Column("conflicts", sa.Boolean(), nullable=False),
        sa.Column("quiet_enabled", sa.Boolean(), nullable=False),
        sa.Column("quiet_start", sa.String(5), nullable=False),
        sa.Column("quiet_end", sa.String(5), nullable=False),
    )
    op.create_table(
        "notification_reads",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("read_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_notification_reads_read_at", "notification_reads", ["read_at"])


def downgrade():
    op.drop_table("notification_reads")
    op.drop_table("notification_preferences")
