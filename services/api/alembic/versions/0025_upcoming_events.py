"""Explicit opt-in for in-app upcoming calendar notices."""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"


def upgrade():
    op.add_column(
        "notification_preferences",
        sa.Column("events", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("notification_preferences", "events")
