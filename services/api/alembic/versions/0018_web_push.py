"""Opt-in Web Push signing, encrypted devices and opaque delivery claims."""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"


def upgrade():
    op.create_table(
        "push_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_key", sa.String(), nullable=False),
        sa.Column("private_key", sa.LargeBinary(), nullable=False),
        sa.Column("contact", sa.String(254), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_table(
        "push_devices",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("endpoint_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("subscription", sa.LargeBinary(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("last_seen", sa.Float(), nullable=False),
        sa.Column("cooldown_until", sa.Float(), nullable=False),
        sa.Column("last_error", sa.String(), nullable=True),
    )
    op.create_table(
        "push_deliveries",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "device_id",
            sa.String(),
            sa.ForeignKey("push_devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt", sa.Float(), nullable=False),
        sa.Column("sent", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_push_deliveries_device_id", "push_deliveries", ["device_id"])
    op.create_index("ix_push_deliveries_created_at", "push_deliveries", ["created_at"])


def downgrade():
    op.drop_table("push_deliveries")
    op.drop_table("push_devices")
    op.drop_table("push_config")
