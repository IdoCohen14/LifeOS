"""Single-use OAuth states bound to account/session/provider revision."""

import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"


def upgrade():
    op.create_table(
        "account_oauth_states",
        sa.Column("state_hash", sa.String(), primary_key=True),
        sa.Column("account_id", sa.String(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column(
            "session_hash",
            sa.String(),
            sa.ForeignKey("sessions.token_hash", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("verifier", sa.LargeBinary(), nullable=False),
        sa.Column("redirect_uri", sa.String(), nullable=False),
        sa.Column("expires", sa.Integer(), nullable=False),
    )
    op.create_index("ix_account_oauth_states_expires", "account_oauth_states", ["expires"])


def downgrade():
    op.drop_table("account_oauth_states")
