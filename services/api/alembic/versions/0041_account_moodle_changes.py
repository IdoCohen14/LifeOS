"""Owned Moodle feed observations."""

import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"


def upgrade():
    op.create_table(
        "account_moodle_changes",
        sa.Column("account_id", sa.String(), sa.ForeignKey("accounts.id"), primary_key=True),
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("event_id", sa.String(256), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("previous", sa.Text(), nullable=True),
        sa.Column("current", sa.Text(), nullable=True),
        sa.Column("observed_at", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_account_moodle_changes_observed_at", "account_moodle_changes", ["observed_at"]
    )


def downgrade():
    op.drop_table("account_moodle_changes")
