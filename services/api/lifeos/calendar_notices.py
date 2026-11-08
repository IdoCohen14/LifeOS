"""Upcoming calendar notices from existing snapshots; no inference or provider requests."""

import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from .briefings import BriefingProblem, iter_cached_calendar
from .models import Settings
from .recommendations import stable_id


def upcoming_events(engine, now):
    deadline = time.monotonic() + 10
    items = []
    try:
        with Session(engine) as db:
            db.execute(text("BEGIN"))
            zone = ZoneInfo(db.get(Settings, 1).timezone)
            today = now.astimezone(zone).date()
            for event in iter_cached_calendar(db, deadline, include_titles=True):
                if event.get("source") in ("assignment", "exam"):
                    continue
                all_day = event.get("all_day", False)
                if all_day:
                    start = date.fromisoformat(event["start"])
                    if (start - today).days not in (0, 1):
                        continue
                    order = start.isoformat()
                else:
                    start = datetime.fromisoformat(event["start"].replace("Z", "+00:00"))
                    if not now <= start < now + timedelta(hours=24):
                        continue
                    order = start.astimezone(timezone.utc).isoformat()
                items.append(
                    {
                        "id": stable_id(
                            "upcoming_event",
                            [
                                event["id"],
                                event.get("title", ""),
                                event["start"],
                                event["end"],
                                zone.key,
                            ],
                        ),
                        "kind": "upcoming_event",
                        "title": event.get("title", ""),
                        "start": event["start"],
                        **({"end": event["end"]} if not all_day else {}),
                        "target": "calendar",
                        "source_ids": [event["id"]],
                        "event_source": event.get("source", "personal"),
                        "priority": 3,
                        "order": order,
                    }
                )
    except BriefingProblem:
        raise HTTPException(503, "notifications_resource_limit") from None
    return items
