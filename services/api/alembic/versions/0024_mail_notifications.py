"""Explicit opt-in for local in-app mail notifications."""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"


def upgrade():
    op.add_column(
        "notification_preferences",
        sa.Column("mail", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("notification_preferences", "mail")
