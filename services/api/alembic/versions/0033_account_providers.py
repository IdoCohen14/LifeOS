"""Per-account encrypted provider state and isolated cached records."""

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"


def upgrade():
    op.create_table(
        "account_providers",
        sa.Column("account_id", sa.String(), sa.ForeignKey("accounts.id"), primary_key=True),
        sa.Column("provider", sa.String(16), primary_key=True),
        sa.Column("credentials", sa.LargeBinary(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("checkpoint", sa.Text(), nullable=True),
        sa.Column("lease_owner", sa.String(), nullable=True),
        sa.Column("lease_until", sa.Integer(), nullable=False),
        sa.Column("last_success", sa.Integer(), nullable=True),
    )
    op.create_table(
        "account_provider_records",
        sa.Column("account_id", sa.String(), primary_key=True),
        sa.Column("provider", sa.String(16), primary_key=True),
        sa.Column("external_id", sa.String(256), primary_key=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id", "provider"],
            ["account_providers.account_id", "account_providers.provider"],
            ondelete="CASCADE",
        ),
    )


def downgrade():
    op.drop_table("account_provider_records")
    op.drop_table("account_providers")
