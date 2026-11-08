"""Explicit operational weekday defaults, preserving all-days compatibility."""

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"


def upgrade():
    op.add_column(
        "planning_preferences",
        sa.Column("weekdays", sa.JSON(), nullable=False, server_default="[1,2,3,4,5,6,7]"),
    )


def downgrade():
    op.drop_column("planning_preferences", "weekdays")
