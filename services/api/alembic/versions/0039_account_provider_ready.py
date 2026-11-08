"""Only authorized account connections enter the background queue."""

import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"


def upgrade():
    op.add_column(
        "account_providers",
        sa.Column("authorized", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.execute("ALTER TABLE account_providers DROP COLUMN authorized")
