"""Reviewed date-forward deletion of weekly personal occurrences, with edited protection."""

import json
import time
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.orm import Session

from .models import CalendarEvent
from .recurring_events import Confirmation, active
from .series_models import EventSeries, SeriesDeleteProposal, SeriesOccurrence, event_signature


def current_time():
    return datetime.now(timezone.utc)


def budget(deadline):
    if time.monotonic() >= deadline:
        raise HTTPException(503, "series_resource_limit")


class DeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    from_day: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    include_modified: bool = False

    @field_validator("from_day")
    @classmethod
    def day_valid(cls, value):
        return date.fromisoformat(value).isoformat()


def eligible(event, from_day, zone, now):
    if event.all_day:
        return event.start >= from_day
    start = datetime.fromisoformat(event.start.replace("Z", "+00:00"))
    return start > now and start.astimezone(zone).date().isoformat() >= from_day


class SeriesManagementService:
    def __init__(self, engine, *, account_id=None):
        self.engine, self.account_id = engine, account_id

    def listing(self, cursor=None):
        with Session(self.engine) as db:
            db.execute(text("BEGIN"))
            from .account_records import AccountRecords

            if self.account_id is not None:
                AccountRecords(self.engine).authorize(db, self.account_id)
            query = select(EventSeries).where(EventSeries.account_id == self.account_id)
            if cursor:
                previous = db.get(EventSeries, cursor)
                if previous is None or previous.account_id != self.account_id:
                    raise HTTPException(409, "series_changed")
                query = query.where(
                    or_(
                        EventSeries.created_at < previous.created_at,
                        (EventSeries.created_at == previous.created_at)
                        & (EventSeries.id < previous.id),
                    )
                )
            rows = list(
                db.scalars(
                    query.order_by(EventSeries.created_at.desc(), EventSeries.id.desc()).limit(21)
                )
            )
            items = [
                {
                    "id": row.id,
                    "title": row.title,
                    "timezone": row.timezone,
                    "count": db.scalar(
                        select(func.count())
                        .select_from(SeriesOccurrence)
                        .where(SeriesOccurrence.series_id == row.id)
                    ),
                }
                for row in rows[:20]
            ]
            return {"items": items, "next_cursor": rows[19].id if len(rows) > 20 else None}

    def preview(self, id, body, session_hash):
        deadline = time.monotonic() + 5
        now = current_time()
        with Session(self.engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            active(db, session_hash, self.account_id)
            series = db.get(EventSeries, id)
            if series is None or series.account_id != self.account_id:
                raise HTTPException(404, "series_missing")
            zone = ZoneInfo(series.timezone)
            today = now.astimezone(zone).date()
            if not today <= date.fromisoformat(body.from_day) <= today + timedelta(days=400):
                raise HTTPException(422, "series_day_range")
            rows = list(
                db.execute(
                    select(SeriesOccurrence, CalendarEvent)
                    .join(CalendarEvent)
                    .where(
                        SeriesOccurrence.series_id == id,
                        CalendarEvent.account_id == self.account_id,
                    )
                    .order_by(CalendarEvent.start, CalendarEvent.id)
                    .limit(53)
                )
            )
            if len(rows) > 52:
                raise HTTPException(503, "series_resource_limit")
            shown = []
            selected = []
            skipped = 0
            for link, event in rows:
                budget(deadline)
                if not eligible(event, body.from_day, zone, now):
                    continue
                signature = event_signature(event)
                unknown = link.original_signature is None
                modified = not unknown and signature != link.original_signature
                if (unknown or modified) and not body.include_modified:
                    skipped += 1
                    continue
                shown.append(
                    {
                        "id": event.id,
                        "title": event.title,
                        "start": event.start,
                        "end": event.end,
                        "all_day": event.all_day,
                        "modified": modified,
                        "unknown": unknown,
                    }
                )
                selected.append({"id": event.id, "signature": signature})
            if not selected:
                return {
                    "id": None,
                    "timezone": series.timezone,
                    "title": series.title,
                    "events": [],
                    "skipped_modified": skipped,
                }
            stamp = int(time.time())
            db.execute(
                delete(SeriesDeleteProposal).where(
                    (
                        (SeriesDeleteProposal.deleted_count.is_(None))
                        & (SeriesDeleteProposal.expires < stamp)
                    )
                    | (SeriesDeleteProposal.confirmed_at < stamp - 30 * 86400)
                )
            )
            if (
                db.scalar(
                    select(func.count())
                    .select_from(SeriesDeleteProposal)
                    .where(
                        SeriesDeleteProposal.session_hash == session_hash,
                        SeriesDeleteProposal.deleted_count.is_(None),
                    )
                )
                >= 20
            ):
                raise HTTPException(429, "series_pending_limit")
            proposal_id = str(uuid4())
            db.add(
                SeriesDeleteProposal(
                    id=proposal_id,
                    session_hash=session_hash,
                    series_id=id,
                    payload=json.dumps(
                        {"zone": series.timezone, "from_day": body.from_day, "items": selected}
                    ),
                    expires=stamp + 900,
                )
            )
            db.flush()
            budget(deadline)
            active(db, session_hash, self.account_id)
            db.commit()
            return {
                "id": proposal_id,
                "timezone": series.timezone,
                "title": series.title,
                "events": shown,
                "skipped_modified": skipped,
            }

    def confirm(self, id, session_hash):
        deadline = time.monotonic() + 5
        with Session(self.engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            active(db, session_hash, self.account_id)
            proposal = db.get(SeriesDeleteProposal, id)
            if not proposal or proposal.session_hash != session_hash:
                raise HTTPException(404, "series_preview_expired")
            if proposal.deleted_count is not None:
                return {"deleted_count": proposal.deleted_count}
            if proposal.expires <= time.time():
                raise HTTPException(404, "series_preview_expired")
            stored = json.loads(proposal.payload)
            series = db.get(EventSeries, proposal.series_id)
            if (
                not series
                or series.account_id != self.account_id
                or series.timezone != stored["zone"]
            ):
                raise HTTPException(409, "series_changed")
            zone = ZoneInfo(stored["zone"])
            now = current_time()
            if date.fromisoformat(stored["from_day"]) < now.astimezone(zone).date():
                raise HTTPException(409, "series_changed")
            sources = []
            for item in stored["items"]:
                budget(deadline)
                link = db.get(SeriesOccurrence, item["id"])
                event = db.get(CalendarEvent, item["id"])
                if (
                    not link
                    or link.series_id != series.id
                    or not event
                    or event.account_id != self.account_id
                    or event_signature(event) != item["signature"]
                    or not eligible(event, stored["from_day"], zone, now)
                ):
                    raise HTTPException(409, "series_changed")
                sources.append(event)
            for event in sources:
                db.delete(event)
            proposal.deleted_count = len(sources)
            proposal.confirmed_at = int(time.time())
            db.flush()
            budget(deadline)
            active(db, session_hash, self.account_id)
            final_now = current_time()
            if (
                proposal.expires <= time.time()
                or date.fromisoformat(stored["from_day"]) < final_now.astimezone(zone).date()
                or any(
                    not eligible(event, stored["from_day"], zone, final_now) for event in sources
                )
            ):
                raise HTTPException(409, "series_changed")
            db.commit()
            return {"deleted_count": len(sources)}

    def cancel(self, id, session_hash):
        with Session(self.engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            active(db, session_hash, self.account_id)
            row = db.get(SeriesDeleteProposal, id)
            if not row or row.session_hash != session_hash:
                raise HTTPException(404, "series_preview_expired")
            if row.deleted_count is not None:
                raise HTTPException(409, "series_already_deleted")
            db.delete(row)
            db.commit()


def series_router(engine, authenticated):
    service = SeriesManagementService(engine)
    router = APIRouter(prefix="/recurrence", dependencies=[Depends(authenticated)])

    @router.get("/series")
    def listing(cursor: str | None = Query(default=None, pattern=r"^[0-9a-f-]{36}$")):
        return service.listing(cursor)

    @router.post("/series/{id}/deletion-preview")
    def preview(id: str, body: DeleteInput, session=Depends(authenticated)):
        return service.preview(id, body, session.token_hash)

    @router.post("/deletions/confirm")
    def confirm(body: Confirmation, session=Depends(authenticated)):
        return service.confirm(body.id, session.token_hash)

    @router.delete("/deletions/{id}", status_code=204)
    def cancel(id: str, session=Depends(authenticated)):
        service.cancel(id, session.token_hash)

    return router
