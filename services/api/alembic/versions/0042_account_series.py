"""Own finite event series without recreating referenced tables."""

from alembic import op

revision = "0042"
down_revision = "0041"


def upgrade():
    op.execute("ALTER TABLE event_series ADD COLUMN account_id VARCHAR REFERENCES accounts(id)")
    op.create_index("ix_event_series_account_id", "event_series", ["account_id"])


def downgrade():
    op.drop_index("ix_event_series_account_id", table_name="event_series")
    op.execute("ALTER TABLE event_series DROP COLUMN account_id")
