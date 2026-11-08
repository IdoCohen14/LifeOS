"""Initial local workspace schema.

This migration is intentionally explicit: later model changes must not alter history.
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None


def upgrade():
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False),
        sa.Column("due", sa.String(), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    for column in ("priority", "due", "completed"):
        op.create_index(f"ix_tasks_{column}", "tasks", [column])
    op.create_table(
        "events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("start", sa.String(), nullable=False),
        sa.Column("end", sa.String(), nullable=False),
        sa.Column("all_day", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    for column in ("start", "end"):
        op.create_index(f"ix_events_{column}", "events", [column])
    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("theme", sa.String(10), nullable=False),
        sa.Column("timezone", sa.String(80), nullable=False),
    )
    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(), primary_key=True),
        sa.Column("csrf", sa.String(), nullable=False),
        sa.Column("expires", sa.Integer(), nullable=False),
    )
    op.create_index("ix_sessions_expires", "sessions", ["expires"])


def downgrade():
    for table in ("sessions", "settings", "events", "tasks"):
        op.drop_table(table)
