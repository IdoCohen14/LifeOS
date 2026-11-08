"""Independent explicit assistant consent; existing saved values unchanged."""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"


def upgrade():
    op.add_column(
        "planning_preferences",
        sa.Column("assistant_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("planning_preferences", "assistant_enabled")
