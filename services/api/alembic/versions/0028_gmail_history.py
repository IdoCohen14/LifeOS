"""Gmail incremental snapshot checkpoint."""

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"


def upgrade():
    op.add_column("gmail_connection", sa.Column("history_id", sa.String(), nullable=True))


def downgrade():
    op.drop_column("gmail_connection", "history_id")
