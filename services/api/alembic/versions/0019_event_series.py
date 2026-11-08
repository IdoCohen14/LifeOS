"""Authoritative approved weekly mappings; no similarity-based group inference."""

import json
from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"


def upgrade():
    op.create_table(
        "event_series",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("timezone", sa.String(80), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index("ix_event_series_created_at", "event_series", ["created_at"])
    op.create_table(
        "series_occurrences",
        sa.Column(
            "event_id",
            sa.String(),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "series_id",
            sa.String(),
            sa.ForeignKey("event_series.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_signature", sa.String(64), nullable=True),
    )
    op.create_index("ix_series_occurrences_series_id", "series_occurrences", ["series_id"])
    op.create_table(
        "series_delete_proposals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "session_hash",
            sa.String(),
            sa.ForeignKey("sessions.token_hash", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("series_id", sa.String(), nullable=False),
        sa.Column("payload", sa.String(), nullable=False),
        sa.Column("expires", sa.Integer(), nullable=False),
        sa.Column("deleted_count", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_series_delete_proposals_session_hash", "series_delete_proposals", ["session_hash"]
    )
    op.create_index("ix_series_delete_proposals_expires", "series_delete_proposals", ["expires"])
    op.execute(
        "CREATE TRIGGER cleanup_empty_series AFTER DELETE ON series_occurrences BEGIN DELETE FROM event_series WHERE id=OLD.series_id AND NOT EXISTS (SELECT 1 FROM series_occurrences WHERE series_id=OLD.series_id); END"
    )
    connection = op.get_bind()
    for row in connection.execute(
        sa.text(
            "SELECT id,payload,event_ids FROM recurrence_proposals WHERE event_ids IS NOT NULL ORDER BY expires,id"
        )
    ):
        try:
            body = json.loads(row.payload)
            if not isinstance(body, dict):
                continue
            ids = json.loads(row.event_ids)
            if (
                str(UUID(row.id)) != row.id
                or not isinstance(ids, list)
                or not 2 <= len(ids) <= 52
                or len(set(ids)) != len(ids)
            ):
                continue
            if (
                not isinstance(body.get("title"), str)
                or not body["title"].strip()
                or len(body["title"]) > 240
            ):
                continue
            zone = ZoneInfo(body["timezone"])
            present = []
            for id in ids:
                if not isinstance(id, str) or str(UUID(id)) != id:
                    raise ValueError()
                event = connection.execute(
                    sa.text(
                        "SELECT id,created_at FROM events WHERE id=:id AND NOT EXISTS (SELECT 1 FROM series_occurrences WHERE event_id=:id)"
                    ),
                    {"id": id},
                ).first()
                if event:
                    present.append(event)
            if not present:
                continue
            created = datetime.fromisoformat(
                min(event.created_at for event in present).replace("Z", "+00:00")
            )
            if created.utcoffset() is None:
                continue
            connection.execute(
                sa.text(
                    "INSERT INTO event_series(id,title,timezone,created_at) VALUES(:id,:title,:zone,:created)"
                ),
                {
                    "id": row.id,
                    "title": body["title"].strip(),
                    "zone": zone.key,
                    "created": created.astimezone(timezone.utc).isoformat(),
                },
            )
            for event in present:
                connection.execute(
                    sa.text(
                        "INSERT INTO series_occurrences(event_id,series_id,original_signature) VALUES(:event,:series,NULL)"
                    ),
                    {"event": event.id, "series": row.id},
                )
        except (ValueError, TypeError, KeyError):
            continue
    op.execute("UPDATE recurrence_proposals SET payload='{}' WHERE event_ids IS NOT NULL")


def downgrade():
    op.execute("DROP TRIGGER cleanup_empty_series")
    op.drop_table("series_delete_proposals")
    op.drop_table("series_occurrences")
    op.drop_table("event_series")
