"""Account provider retry scheduling and safe error codes."""

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"


def upgrade():
    op.add_column("account_providers", sa.Column("last_attempt", sa.Integer(), nullable=True))
    op.add_column("account_providers", sa.Column("error", sa.String(80), nullable=True))
    op.add_column(
        "account_providers", sa.Column("failures", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "account_providers",
        sa.Column("next_sync", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    for column in ("next_sync", "failures", "error", "last_attempt"):
        op.execute(f"ALTER TABLE account_providers DROP COLUMN {column}")
