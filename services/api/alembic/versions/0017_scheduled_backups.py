"""Default-off unattended backup config and automatic-file retention registry."""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"


def upgrade():
    op.create_table(
        "backup_schedule",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("clock", sa.String(5), nullable=False),
        sa.Column("keep", sa.Integer(), nullable=False),
        sa.Column("encrypted_password", sa.LargeBinary(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("last_attempt", sa.Float(), nullable=True),
        sa.Column("last_success", sa.Float(), nullable=True),
        sa.Column("last_day", sa.String(), nullable=True),
        sa.Column("last_zone", sa.String(), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
    )
    op.create_table(
        "automatic_backup_files",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.Float(), nullable=False),
    )
    op.create_index(
        "ix_automatic_backup_files_created_at", "automatic_backup_files", ["created_at"]
    )


def downgrade():
    op.drop_table("automatic_backup_files")
    op.drop_table("backup_schedule")
