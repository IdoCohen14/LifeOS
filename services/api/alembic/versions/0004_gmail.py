"""Separate read-only Gmail credentials, OAuth state and bounded Inbox cache."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade():
    op.create_table(
        "gmail_connection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("credentials", sa.LargeBinary(), nullable=True),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("last_success", sa.Integer(), nullable=True),
        sa.Column("next_sync", sa.Integer(), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(), nullable=True),
        sa.Column("lease_until", sa.Integer(), nullable=False),
    )
    op.create_table(
        "gmail_oauth_states",
        sa.Column("state_hash", sa.String(), primary_key=True),
        sa.Column(
            "session_hash",
            sa.String(),
            sa.ForeignKey("sessions.token_hash", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("verifier", sa.LargeBinary(), nullable=False),
        sa.Column("redirect_uri", sa.String(), nullable=False),
        sa.Column("expires", sa.Integer(), nullable=False),
    )
    op.create_table(
        "gmail_messages",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("payload", sa.String(), nullable=False),
    )


def downgrade():
    op.drop_table("gmail_messages")
    op.drop_table("gmail_oauth_states")
    op.drop_table("gmail_connection")
