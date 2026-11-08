"""Local mail review markers owned by account/provider generation."""

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"


def upgrade():
    op.create_table(
        "account_mail_reviews",
        sa.Column("account_id", sa.String(), sa.ForeignKey("accounts.id"), primary_key=True),
        sa.Column("provider_revision", sa.Integer(), primary_key=True),
        sa.Column("message_id", sa.String(256), primary_key=True),
    )


def downgrade():
    op.drop_table("account_mail_reviews")
