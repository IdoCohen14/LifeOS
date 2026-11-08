"""Owned scheduled briefing snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "account_briefings",
        sa.Column("account_id", sa.String(), sa.ForeignKey("accounts.id"), primary_key=True),
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("period_start", sa.String(10), nullable=False),
        sa.Column("timezone", sa.String(80), nullable=False),
        sa.Column("generated_at", sa.String(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_index("ix_account_briefings_generated_at", "account_briefings", ["generated_at"])


def downgrade():
    op.drop_table("account_briefings")
