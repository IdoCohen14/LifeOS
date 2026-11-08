"""Reviewed finite weekly title and date/time changes, with explicit approval."""

import json
import time
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, model_validator
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from .assistant import local_instant
from .models import CalendarEvent
from .recurring_events import Confirmation, active
from .series_management import DeleteInput, eligible
from .series_models import EventSeries, SeriesOccurrence, SeriesRescheduleProposal, event_signature


def current_time():
    return datetime.now(timezone.utc)


def budget(deadline):
    if time.monotonic() >= deadline:
        raise HTTPException(503, "series_resource_limit")


class RescheduleInput(DeleteInput):
    clock: str | None = Field(default=None, pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    duration: int | None = Field(default=None, ge=5, le=720, multiple_of=5)
    day_shift: int = Field(default=0, ge=-28, le=28)
    preserve_time: bool = False
    shift_and_time: bool = False
    include_all_day: bool = False
    target_all_day: bool | None = None
    new_title: str | None = Field(default=None, min_length=1, max_length=240)

    @model_validator(mode="after")
    def distinct_modes(self):
        if self.new_title is not None:
            self.new_title = self.new_title.strip()
            if (
                not self.new_title
                or self.target_all_day is not None
                or self.shift_and_time
                or self.preserve_time
                or self.include_all_day
                or self.day_shift
                or self.clock is not None
                or self.duration is not None
            ):
                raise ValueError("series_title_mode")
        elif self.target_all_day is not None:
            if self.shift_and_time or self.preserve_time or self.include_all_day or self.day_shift:
                raise ValueError("series_type_mode")
            if self.target_all_day and (self.clock is not None or self.duration is not None):
                raise ValueError("series_type_mode")
            if not self.target_all_day and (self.clock is None or self.duration is None):
                raise ValueError("series_type_mode")
        elif self.shift_and_time:
            if (
                self.preserve_time
                or self.include_all_day
                or self.day_shift == 0
                or self.clock is None
                or self.duration is None
            ):
                raise ValueError("series_combined_mode")
        elif self.preserve_time:
            if self.day_shift == 0 or self.clock is not None or self.duration is not None:
                raise ValueError("series_date_shift_mode")
        elif (
            self.include_all_day
            or self.day_shift != 0
            or self.clock is None
            or self.duration is None
        ):
            raise ValueError("series_clock_mode")
        return self


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def target(event, clock, duration, zone, day_shift=0, preserve_time=False):
    try:
        if event.all_day:
            start_day = date.fromisoformat(event.start) + timedelta(days=day_shift)
            end_day = date.fromisoformat(event.end) + timedelta(days=day_shift)
            if not preserve_time or end_day <= start_day:
                raise ValueError("series_all_day_invalid")
            return start_day.isoformat(), end_day.isoformat()
        original_start = instant(event.start)
        local_start = original_start.astimezone(zone)
        day = (local_start.date() + timedelta(days=day_shift)).isoformat()
        if preserve_time:
            clock = local_start.replace(tzinfo=None).time().isoformat()
        start = local_instant(day, clock, zone)
        if preserve_time:
            elapsed = instant(event.end) - original_start
            end = start + elapsed
            local_end = end.astimezone(zone)
            local_instant(
                local_end.date().isoformat(),
                local_end.replace(tzinfo=None).time().isoformat(),
                zone,
            )
        else:
            wall_end = datetime.fromisoformat(f"{day}T{clock}") + timedelta(minutes=duration)
            end = local_instant(wall_end.date().isoformat(), wall_end.strftime("%H:%M"), zone)
    except OverflowError:
        raise HTTPException(422, "series_time_invalid") from None
    except ValueError:
        raise HTTPException(422, "series_time_ambiguous") from None
    if end <= start:
        raise HTTPException(422, "series_time_ambiguous")
    return start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")


def elapsed_range(day, clock, duration, zone):
    try:
        start = local_instant(day.isoformat(), clock, zone)
        end = start + timedelta(minutes=duration)
        local_end = end.astimezone(zone)
        local_instant(
            local_end.date().isoformat(), local_end.replace(tzinfo=None).time().isoformat(), zone
        )
        if end <= start:
            raise ValueError("invalid_clock_range")
        return start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")
    except OverflowError:
        raise HTTPException(422, "series_time_invalid") from None
    except ValueError:
        raise HTTPException(422, "series_time_ambiguous") from None


def planned_range(event, values, zone):
    """None means a multi-day source is deliberately left for individual editing."""
    if values.get("new_title") is not None:
        return event.start, event.end
    if values.get("shift_and_time", False):
        try:
            day = instant(event.start).astimezone(zone).date() + timedelta(days=values["day_shift"])
            return elapsed_range(day, values["clock"], values["duration"], zone)
        except OverflowError:
            raise HTTPException(422, "series_time_invalid") from None
    desired = values.get("target_all_day")
    if desired is None:
        return target(
            event,
            values["clock"],
            values["duration"],
            zone,
            values.get("day_shift", 0),
            values.get("preserve_time", False),
        )
    try:
        if desired:
            start = instant(event.start).astimezone(zone)
            end = instant(event.end).astimezone(zone)
            day = start.date()
            next_day = day + timedelta(days=1)
            if not (
                end.date() == day
                or (end.date() == next_day and end.time() == datetime.min.time() and end.fold == 0)
            ):
                return None
            return day.isoformat(), next_day.isoformat()
        day = date.fromisoformat(event.start)
        if date.fromisoformat(event.end) - day != timedelta(days=1):
            return None
        return elapsed_range(day, values["clock"], values["duration"], zone)
    except OverflowError:
        raise HTTPException(422, "series_time_invalid") from None
    except ValueError:
        raise HTTPException(422, "series_time_ambiguous") from None


def destination_valid(start, all_day, zone, now):
    if all_day:
        return date.fromisoformat(start) >= now.astimezone(zone).date()
    return instant(start) > now


class SeriesReschedulingService:
    def __init__(self, engine, *, account_id=None):
        self.engine, self.account_id = engine, account_id

    def preview(self, id, body, session_hash):
        deadline = time.monotonic() + 5
        now = current_time()
        renaming = body.new_title is not None
        converting = body.target_all_day is not None
        mode = body.model_dump()
        with Session(self.engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            active(db, session_hash, self.account_id)
            series = db.get(EventSeries, id)
            if not series:
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
            shown, selected = [], []
            skipped = {
                "skipped_modified": 0,
                "skipped_all_day": 0,
                "skipped_unchanged": 0,
                "skipped_multiday": 0,
            }
            for link, event in rows:
                budget(deadline)
                if not eligible(event, body.from_day, zone, now):
                    continue
                if event.all_day and not (body.include_all_day or renaming or converting):
                    skipped["skipped_all_day"] += 1
                    continue
                signature = event_signature(event)
                unknown = link.original_signature is None
                modified = not unknown and signature != link.original_signature
                if (unknown or modified) and not body.include_modified:
                    skipped["skipped_modified"] += 1
                    continue
                if converting and event.all_day == body.target_all_day:
                    skipped["skipped_unchanged"] += 1
                    continue
                proposed = planned_range(event, mode, zone)
                if proposed is None:
                    skipped["skipped_multiday"] += 1
                    continue
                start, end = proposed
                new_all_day = body.target_all_day if converting else event.all_day
                if not destination_valid(start, new_all_day, zone, now):
                    raise HTTPException(422, "series_start_past")
                if not converting:
                    same_range = (start, end) == (event.start, event.end) or (
                        not event.all_day
                        and instant(start) == instant(event.start)
                        and instant(end) == instant(event.end)
                    )
                    if (renaming and body.new_title == event.title) or (
                        not renaming and same_range
                    ):
                        skipped["skipped_unchanged"] += 1
                        continue
                shown.append(
                    {
                        "id": event.id,
                        "title": event.title,
                        "start": event.start,
                        "end": event.end,
                        "new_all_day": new_all_day,
                        "new_title": body.new_title,
                        "new_start": start,
                        "new_end": end,
                        "all_day": event.all_day,
                        "modified": modified,
                        "unknown": unknown,
                    }
                )
                selected.append(
                    {
                        "id": event.id,
                        "signature": signature,
                        "original_signature": link.original_signature,
                        "title": body.new_title if renaming else event.title,
                        "all_day": new_all_day,
                        "start": start,
                        "end": end,
                    }
                )
            result = {
                "id": None,
                "title": series.title,
                "timezone": series.timezone,
                "events": shown,
                **skipped,
            }
            budget(deadline)
            if not selected:
                return result
            stamp = int(time.time())
            db.execute(
                delete(SeriesRescheduleProposal).where(
                    (
                        (SeriesRescheduleProposal.changed_count.is_(None))
                        & (SeriesRescheduleProposal.expires < stamp)
                    )
                    | (SeriesRescheduleProposal.confirmed_at < stamp - 30 * 86400)
                )
            )
            pending = db.scalar(
                select(func.count())
                .select_from(SeriesRescheduleProposal)
                .where(
                    SeriesRescheduleProposal.session_hash == session_hash,
                    SeriesRescheduleProposal.changed_count.is_(None),
                )
            )
            if pending >= 20:
                raise HTTPException(429, "series_pending_limit")
            proposal_id = str(uuid4())
            db.add(
                SeriesRescheduleProposal(
                    id=proposal_id,
                    session_hash=session_hash,
                    series_id=id,
                    payload=json.dumps(
                        {
                            "shift_and_time": body.shift_and_time,
                            "target_all_day": body.target_all_day,
                            "new_title": body.new_title,
                            "zone": series.timezone,
                            "from_day": body.from_day,
                            "clock": body.clock,
                            "duration": body.duration,
                            "day_shift": body.day_shift,
                            "preserve_time": body.preserve_time,
                            "include_all_day": body.include_all_day,
                            "items": selected,
                        }
                    ),
                    expires=stamp + 900,
                )
            )
            db.flush()
            budget(deadline)
            active(db, session_hash, self.account_id)
            db.commit()
            result["id"] = proposal_id
            return result

    def confirm(self, id, session_hash):
        deadline = time.monotonic() + 5
        with Session(self.engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            active(db, session_hash, self.account_id)
            proposal = db.get(SeriesRescheduleProposal, id)
            if not proposal or proposal.session_hash != session_hash:
                raise HTTPException(404, "series_preview_expired")
            if proposal.changed_count is not None:
                return {"changed_count": proposal.changed_count}
            if proposal.expires <= time.time():
                raise HTTPException(404, "series_preview_expired")
            stored = json.loads(proposal.payload)
            renaming = stored.get("new_title") is not None
            converting = stored.get("target_all_day") is not None
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
            starts = []
            days = []
            for item in stored["items"]:
                budget(deadline)
                link = db.get(SeriesOccurrence, item["id"])
                event = db.get(CalendarEvent, item["id"])
                if (
                    not link
                    or link.series_id != series.id
                    or not event
                    or event.account_id != self.account_id
                    or (
                        event.all_day
                        and not (
                            renaming
                            or converting
                            or (
                                stored.get("include_all_day", False)
                                and stored.get("preserve_time", False)
                            )
                        )
                    )
                    or event_signature(event) != item["signature"]
                    or link.original_signature != item["original_signature"]
                    or not eligible(event, stored["from_day"], zone, now)
                ):
                    raise HTTPException(409, "series_changed")
                try:
                    proposed = planned_range(event, stored, zone)
                except HTTPException:
                    raise HTTPException(409, "series_changed") from None
                if item.get("title", event.title) != (
                    stored["new_title"] if renaming else event.title
                ):
                    raise HTTPException(409, "series_changed")
                new_all_day = stored["target_all_day"] if converting else event.all_day
                if item.get("all_day", event.all_day) != new_all_day:
                    raise HTTPException(409, "series_changed")
                if proposed != (item["start"], item["end"]) or not destination_valid(
                    item["start"], new_all_day, zone, now
                ):
                    raise HTTPException(409, "series_changed")
                for value, all_day in ((event.start, event.all_day), (item["start"], new_all_day)):
                    if all_day:
                        days.append(date.fromisoformat(value))
                    else:
                        starts.append(instant(value))
                sources.append((event, link, item))
            for event, link, item in sources:
                event.start, event.end = item["start"], item["end"]
                event.title = item.get("title", event.title)
                event.all_day = item.get("all_day", event.all_day)
                if item["signature"] == item["original_signature"]:
                    link.original_signature = event_signature(event)
            proposal.changed_count = len(sources)
            proposal.confirmed_at = int(time.time())
            proposal.payload = "{}"
            db.flush()
            budget(deadline)
            active(db, session_hash, self.account_id)
            final_now = current_time()
            if (
                proposal.expires <= time.time()
                or date.fromisoformat(stored["from_day"]) < final_now.astimezone(zone).date()
                or any(value <= final_now for value in starts)
                or any(value < final_now.astimezone(zone).date() for value in days)
            ):
                raise HTTPException(409, "series_changed")
            db.commit()
            return {"changed_count": len(sources)}

    def cancel(self, id, session_hash):
        with Session(self.engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            active(db, session_hash, self.account_id)
            row = db.get(SeriesRescheduleProposal, id)
            if not row or row.session_hash != session_hash:
                raise HTTPException(404, "series_preview_expired")
            if row.changed_count is not None:
                raise HTTPException(409, "series_already_changed")
            db.delete(row)
            db.commit()


def rescheduling_router(engine, authenticated):
    service = SeriesReschedulingService(engine)
    router = APIRouter(prefix="/recurrence", dependencies=[Depends(authenticated)])

    @router.post("/series/{id}/reschedule-preview")
    def preview(id: str, body: RescheduleInput, session=Depends(authenticated)):
        return service.preview(id, body, session.token_hash)

    @router.post("/reschedules/confirm")
    def confirm(body: Confirmation, session=Depends(authenticated)):
        return service.confirm(body.id, session.token_hash)

    @router.delete("/reschedules/{id}", status_code=204)
    def cancel(id: str, session=Depends(authenticated)):
        service.cancel(id, session.token_hash)

    return router
