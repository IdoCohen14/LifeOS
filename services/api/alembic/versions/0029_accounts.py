"""Inactive account identity foundation; legacy sessions stay unassigned."""

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"


def upgrade():
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("login", sa.String(254), nullable=False, unique=True),
        sa.Column("password_digest", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )
    # Keep session-referencing proposals/OAuth states intact under SQLite FK enforcement.
    op.execute(
        "ALTER TABLE sessions ADD COLUMN account_id VARCHAR REFERENCES accounts(id) ON DELETE CASCADE"
    )
    op.create_index("ix_sessions_account_id", "sessions", ["account_id"])


def downgrade():
    op.drop_index("ix_sessions_account_id", table_name="sessions")
    op.execute("ALTER TABLE sessions DROP COLUMN account_id")
    op.drop_table("accounts")
