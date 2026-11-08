"""Observed Moodle calendar export changes."""

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"


def upgrade():
    op.create_table(
        "moodle_changes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("previous", sa.String(), nullable=True),
        sa.Column("current", sa.String(), nullable=True),
        sa.Column("observed_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_moodle_changes_observed_at", "moodle_changes", ["observed_at"])


def downgrade():
    op.drop_index("ix_moodle_changes_observed_at", table_name="moodle_changes")
    op.drop_table("moodle_changes")
