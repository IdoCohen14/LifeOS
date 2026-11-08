"""Account-specific preference storage; no legacy preference copying."""

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"


def upgrade():
    op.create_table(
        "account_preferences",
        sa.Column("account_id", sa.String(), sa.ForeignKey("accounts.id"), primary_key=True),
        sa.Column("kind", sa.String(32), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )


def downgrade():
    op.drop_table("account_preferences")
