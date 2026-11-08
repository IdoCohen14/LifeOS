"""Read-only Google Calendar credentials, provenance, checkpoints and OAuth states."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade():
    op.create_table(
        "google_connection",
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
        "google_oauth_states",
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
        "google_calendars",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("timezone", sa.String(), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("sync_token", sa.String(), nullable=True),
    )
    op.create_table(
        "google_records",
        sa.Column(
            "calendar_id",
            sa.String(),
            sa.ForeignKey("google_calendars.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("external_id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), primary_key=True),
        sa.Column("payload", sa.Text(), nullable=False),
    )


def downgrade():
    for table in ("google_records", "google_calendars", "google_oauth_states", "google_connection"):
        op.drop_table(table)
