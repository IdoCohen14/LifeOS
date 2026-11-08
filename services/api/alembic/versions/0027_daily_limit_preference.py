"""Explicit optional daily calendar occupancy preference."""

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"


def upgrade():
    op.add_column(
        "planning_preferences", sa.Column("daily_limit_minutes", sa.Integer(), nullable=True)
    )


def downgrade():
    op.drop_column("planning_preferences", "daily_limit_minutes")
