"""Explicit operational defaults, separate from conversation text."""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"


def upgrade():
    op.create_table(
        "planning_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.String(5), nullable=False),
        sa.Column("window_end", sa.String(5), nullable=False),
    )


def downgrade():
    op.drop_table("planning_preferences")
