"""Encrypted Moodle subscription and bounded read-only calendar snapshot."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade():
    op.create_table(
        "moodle_connection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("credentials", sa.LargeBinary(), nullable=True),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("last_success", sa.Integer(), nullable=True),
        sa.Column("next_sync", sa.Integer(), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(), nullable=True),
        sa.Column("lease_until", sa.Integer(), nullable=False),
    )
    op.create_table(
        "moodle_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("payload", sa.String(), nullable=False),
    )


def downgrade():
    op.drop_table("moodle_events")
    op.drop_table("moodle_connection")
