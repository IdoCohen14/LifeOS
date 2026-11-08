"""Optional one-use recovery keys and explicit account deletion state."""

import sqlalchemy as sa
from alembic import op

revision = "0044"
down_revision = "0043"


def upgrade():
    op.create_table(
        "account_lifecycle",
        sa.Column(
            "account_id",
            sa.String(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("recovery_digest", sa.String(64), nullable=True),
        sa.Column("deletion_preview", sa.Text(), nullable=True),
        sa.Column("deletion_state", sa.String(24), nullable=True),
    )


def downgrade():
    op.drop_table("account_lifecycle")
