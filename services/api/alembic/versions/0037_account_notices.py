"""Owned recommendation dismissal and notification acknowledgement/actions."""

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"


def upgrade():
    op.create_table(
        "account_notice_states",
        sa.Column("account_id", sa.String(), sa.ForeignKey("accounts.id"), primary_key=True),
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("read_at", sa.Integer(), nullable=True),
        sa.Column("dismissed", sa.Boolean(), nullable=False),
        sa.Column("snoozed_until", sa.Integer(), nullable=True),
        sa.Column("recommendation_until", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table("account_notice_states")
