"""Separate account push keys, subscriptions and delivery receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0043"
down_revision = "0042"


def upgrade():
    op.create_table(
        "account_push_config",
        sa.Column("id", sa.String(), sa.ForeignKey("accounts.id"), primary_key=True),
        sa.Column("public_key", sa.String(), nullable=False),
        sa.Column("private_key", sa.LargeBinary(), nullable=False),
        sa.Column("contact", sa.String(254), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_table(
        "account_push_devices",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("account_id", sa.String(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("endpoint_hash", sa.String(64), nullable=False),
        sa.Column("subscription", sa.LargeBinary(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("last_seen", sa.Float(), nullable=False),
        sa.Column("cooldown_until", sa.Float(), nullable=False),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.UniqueConstraint("account_id", "endpoint_hash"),
    )
    op.create_index("ix_account_push_devices_account_id", "account_push_devices", ["account_id"])
    op.create_table(
        "account_push_deliveries",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "device_id",
            sa.String(),
            sa.ForeignKey("account_push_devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt", sa.Float(), nullable=False),
        sa.Column("sent", sa.Boolean(), nullable=False),
    )
    op.create_index(
        "ix_account_push_deliveries_device_id", "account_push_deliveries", ["device_id"]
    )
    op.create_index(
        "ix_account_push_deliveries_created_at", "account_push_deliveries", ["created_at"]
    )


def downgrade():
    op.drop_table("account_push_deliveries")
    op.drop_table("account_push_devices")
    op.drop_table("account_push_config")
