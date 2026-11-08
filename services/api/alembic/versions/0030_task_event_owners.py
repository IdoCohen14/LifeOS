"""Inactive account ownership for manual tasks/events; legacy rows stay unassigned."""

from alembic import op

revision = "0030"
down_revision = "0029"


def upgrade():
    for table in ("tasks", "events"):
        # SQLite supports nullable inline REFERENCES without rebuilding referenced tables.
        # Batch recreation could trigger ON DELETE cascades from academic records.
        op.execute(f"ALTER TABLE {table} ADD COLUMN account_id VARCHAR REFERENCES accounts(id)")
        op.create_index(f"ix_{table}_account_id", table, ["account_id"])


def downgrade():
    for table in ("events", "tasks"):
        op.drop_index(f"ix_{table}_account_id", table_name=table)
        op.execute(f"ALTER TABLE {table} DROP COLUMN account_id")
