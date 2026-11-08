"""Session-owned finite weekly previews; only confirmation writes personal events."""

import json
import time
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import ForeignKey, Integer, String, delete, func, select, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from .assistant import local_instant, scoped_settings, session_scope
from .db import Base
from .models import CalendarEvent
from .schemas import EventInput, TaskInput
from .series_models import EventSeries, SeriesOccurrence, event_signature

MAX_SECONDS = 5


class RecurringProposal(Base):
    __tablename__ = "recurrence_proposals"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_hash: Mapped[str] = mapped_column(
        ForeignKey("sessions.token_hash", ondelete="CASCADE"), index=True
    )
    payload: Mapped[str] = mapped_column(String)
    expires: Mapped[int] = mapped_column(Integer, index=True)
    event_ids: Mapped[str | None] = mapped_column(String, nullable=True)
    confirmed_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class RecurringInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=240, strict=True)
    notes: str = Field(default="", max_length=10000, strict=True)
    day: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    clock: str = Field(default="09:00", pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    duration: int = Field(default=60, ge=5, le=720, multiple_of=5, strict=True)
    count: int = Field(ge=2, le=52, strict=True)
    all_day: bool = Field(default=False, strict=True)
    timezone: str = Field(min_length=1, max_length=80, strict=True)

    @field_validator("title")
    @classmethod
    def title_valid(cls, value):
        return TaskInput.title_not_blank(value)

    @field_validator("day")
    @classmethod
    def day_valid(cls, value):
        return date.fromisoformat(value).isoformat()


class Confirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[0-9a-f-]{36}$")


def current_time():
    return datetime.now(timezone.utc)


def budget(deadline):
    if time.monotonic() >= deadline:
        raise HTTPException(503, "recurrence_resource_limit")


def records(body, zone_name, deadline):
    if body.timezone != zone_name:
        raise HTTPException(409, "recurrence_timezone_changed")
    zone = ZoneInfo(zone_name)
    now = current_time().astimezone(timezone.utc)
    today = now.astimezone(zone).date()
    first = date.fromisoformat(body.day)
    if not today <= first <= today + timedelta(days=30):
        raise HTTPException(422, "recurrence_day_range")
    result = []
    for i in range(body.count):
        budget(deadline)
        day = first + timedelta(weeks=i)
        if body.all_day:
            start, end = day.isoformat(), (day + timedelta(days=1)).isoformat()
        else:
            local_start = datetime.fromisoformat(f"{day.isoformat()}T{body.clock}")
            local_end = local_start + timedelta(minutes=body.duration)
            try:
                start = local_instant(day.isoformat(), body.clock, zone)
                end = local_instant(local_end.date().isoformat(), local_end.strftime("%H:%M"), zone)
            except ValueError:
                raise HTTPException(422, "recurrence_time_ambiguous") from None
            if start <= now:
                raise HTTPException(422, "recurrence_start_past")
            start, end = start.isoformat(), end.isoformat()
        result.append(
            EventInput(
                title=body.title, notes=body.notes, start=start, end=end, all_day=body.all_day
            ).model_dump()
        )
    return result


def active(db, session_hash, account_id=None):
    session_scope(db, session_hash, account_id)


class RecurringEventService:
    def __init__(self, engine, *, account_id=None):
        self.engine, self.account_id = engine, account_id

    def preview(self, body, session_hash):
        deadline = time.monotonic() + MAX_SECONDS
        with Session(self.engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            active(db, session_hash, self.account_id)
            zone_name = scoped_settings(db, self.account_id).timezone
            events = records(body, zone_name, deadline)
            now = int(time.time())
            db.execute(
                delete(RecurringProposal).where(
                    ((RecurringProposal.event_ids.is_(None)) & (RecurringProposal.expires < now))
                    | (RecurringProposal.confirmed_at < now - 30 * 86400)
                )
            )
            count = db.scalar(
                select(func.count())
                .select_from(RecurringProposal)
                .where(
                    RecurringProposal.session_hash == session_hash,
                    RecurringProposal.event_ids.is_(None),
                )
            )
            if count >= 20:
                raise HTTPException(429, "recurrence_pending_limit")
            id = str(uuid4())
            db.add(
                RecurringProposal(
                    id=id,
                    session_hash=session_hash,
                    payload=body.model_dump_json(),
                    expires=now + 900,
                )
            )
            db.flush()
            budget(deadline)
            active(db, session_hash, self.account_id)
            db.commit()
        return {"id": id, "timezone": zone_name, "events": events}

    def confirm(self, id, session_hash):
        deadline = time.monotonic() + MAX_SECONDS
        with Session(self.engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            active(db, session_hash, self.account_id)
            proposal = db.get(RecurringProposal, id)
            if not proposal or proposal.session_hash != session_hash:
                raise HTTPException(404, "recurrence_expired")
            if proposal.event_ids is not None:
                return {"event_ids": json.loads(proposal.event_ids), "series_id": id}
            if proposal.expires <= time.time():
                raise HTTPException(404, "recurrence_expired")
            body = RecurringInput.model_validate_json(proposal.payload)
            events = records(body, scoped_settings(db, self.account_id).timezone, deadline)
            ids = []
            signatures = []
            db.add(
                EventSeries(
                    id=id,
                    account_id=self.account_id,
                    title=body.title,
                    timezone=body.timezone,
                    created_at=current_time().isoformat(),
                )
            )
            for event in events:
                budget(deadline)
                event_id = str(uuid4())
                ids.append(event_id)
                signatures.append((event_id, event_signature(event)))
                db.add(
                    CalendarEvent(
                        id=event_id,
                        account_id=self.account_id,
                        created_at=current_time().isoformat(),
                        **event,
                    )
                )
            db.flush()
            for event_id, signature in signatures:
                db.add(
                    SeriesOccurrence(event_id=event_id, series_id=id, original_signature=signature)
                )
            proposal.payload = "{}"
            proposal.event_ids = json.dumps(ids)
            proposal.confirmed_at = int(time.time())
            db.flush()
            budget(deadline)
            active(db, session_hash, self.account_id)
            if proposal.expires <= time.time():
                raise HTTPException(404, "recurrence_expired")
            # Revalidation after flush fences dates which crossed now during generation.
            records(body, scoped_settings(db, self.account_id).timezone, deadline)
            db.commit()
        return {"event_ids": ids, "series_id": id}

    def cancel(self, id, session_hash):
        with Session(self.engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            active(db, session_hash, self.account_id)
            row = db.get(RecurringProposal, id)
            if not row or row.session_hash != session_hash:
                raise HTTPException(404, "recurrence_expired")
            if row.event_ids is not None:
                raise HTTPException(409, "recurrence_already_confirmed")
            db.delete(row)
            db.commit()


def recurring_router(engine, authenticated):
    service = RecurringEventService(engine)
    router = APIRouter(prefix="/recurrence", dependencies=[Depends(authenticated)])

    @router.post("/preview")
    def preview(body: RecurringInput, session=Depends(authenticated)):
        return service.preview(body, session.token_hash)

    @router.post("/confirm")
    def confirm(body: Confirmation, session=Depends(authenticated)):
        return service.confirm(body.id, session.token_hash)

    @router.delete("/proposals/{id}", status_code=204)
    def cancel(id: str, session=Depends(authenticated)):
        service.cancel(id, session.token_hash)

    return router
