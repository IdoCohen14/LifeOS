"""Minimal observed feed-change history, kept with the local Moodle snapshot."""

import json
from uuid import uuid4

from sqlalchemy import Integer, String, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .moodle_models import MoodleEvent


class MoodleChange(Base):
    __tablename__ = "moodle_changes"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    event_id: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    previous: Mapped[str | None] = mapped_column(String, nullable=True)
    current: Mapped[str | None] = mapped_column(String, nullable=True)
    observed_at: Mapped[int] = mapped_column(Integer, index=True)


def projection(event):
    return {key: event.get(key) for key in ("title", "start", "end", "all_day", "source_url")}


def record_changes(db, events, observed_at, baseline):
    if not baseline:
        previous = {
            row.id: projection(json.loads(row.payload)) for row in db.scalars(select(MoodleEvent))
        }
        current = {event["id"]: projection(event) for event in events}
        for id in sorted(previous.keys() | current.keys()):
            old, new = previous.get(id), current.get(id)
            if old == new:
                continue
            db.add(
                MoodleChange(
                    id=str(uuid4()),
                    event_id=id,
                    kind="added" if old is None else "removed" if new is None else "changed",
                    previous=json.dumps(old) if old is not None else None,
                    current=json.dumps(new) if new is not None else None,
                    observed_at=observed_at,
                )
            )
    db.flush()
    db.execute(delete(MoodleChange).where(MoodleChange.observed_at < observed_at - 30 * 86400))
    keep = (
        select(MoodleChange.id)
        .order_by(MoodleChange.observed_at.desc(), MoodleChange.id)
        .limit(200)
    )
    db.execute(
        delete(MoodleChange)
        .where(MoodleChange.id.not_in(keep))
        .execution_options(synchronize_session=False)
    )


def list_changes(db):
    return [
        {
            "id": row.id,
            "event_id": row.event_id,
            "kind": row.kind,
            "previous": json.loads(row.previous) if row.previous else None,
            "current": json.loads(row.current) if row.current else None,
            "observed_at": row.observed_at,
        }
        for row in db.scalars(
            select(MoodleChange)
            .order_by(MoodleChange.observed_at.desc(), MoodleChange.id)
            .limit(20)
        )
    ]


def change_candidates(engine, now):
    from datetime import datetime, timezone

    from sqlalchemy.orm import Session

    from .recommendations import stable_id

    with Session(engine) as db:
        changes = list_changes(db)
    items = []
    for change in changes:
        if change["observed_at"] < now.timestamp() - 86400:
            continue
        event = change["current"] or change["previous"]
        if not event:
            continue
        previous = change["previous"]
        items.append(
            {
                "id": stable_id("moodle_update", [change["id"]]),
                "kind": "moodle_update",
                "title": event["title"],
                "start": event["start"],
                "target": "calendar",
                "event_source": "moodle",
                "source_ids": [change["event_id"]],
                "change_kind": change["kind"],
                "observed_at": change["observed_at"],
                "previous_start": previous["start"]
                if previous and change["current"] and previous["start"] != event["start"]
                else None,
                "priority": 3,
                "order": datetime.fromtimestamp(change["observed_at"], timezone.utc).isoformat(),
            }
        )
    return items
