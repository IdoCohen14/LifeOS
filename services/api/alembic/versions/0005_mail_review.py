"""Persistent local mail review state; no Gmail mutation."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade():
    op.create_table("gmail_reviewed", sa.Column("id", sa.String(), primary_key=True))


def downgrade():
    op.drop_table("gmail_reviewed")
