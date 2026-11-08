"""Opt-in scheduled numeric planning snapshots from cached records; no network or AI."""

import json
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from .academic_calendar import iter_calendar
from .briefing_models import BriefingSchedule, ScheduledBriefing
from .google_models import GoogleCalendar, GoogleConnection, GoogleRecord
from .models import CalendarEvent, Settings, Task
from .moodle_models import MoodleConnection, MoodleEvent
from .recommendations import stable_id
from .task_scope import actionable_tasks

MAX_EVENTS = 20000
MAX_TASKS = 100000
MAX_SECONDS = 10
CLOCK = r"^(?:[01]\d|2[0-3]):[0-5]\d$"


def current_time():
    return datetime.now(timezone.utc)


class BriefingProblem(ValueError):
    pass


class ScheduleInput(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    daily_enabled: bool = False
    daily_time: str = Field(default="08:00", pattern=CLOCK)
    weekly_enabled: bool = False
    weekly_day: int = Field(default=6, ge=0, le=6)
    weekly_time: str = Field(default="08:00", pattern=CLOCK)


def occurrence(day, clock, zone):
    naive = datetime.fromisoformat(f"{day.isoformat()}T{clock}")
    first = naive.replace(tzinfo=zone, fold=0)
    if (
        first.utcoffset() != naive.replace(tzinfo=zone, fold=1).utcoffset()
        or first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != naive
    ):
        raise BriefingProblem("briefing_schedule_ambiguous")
    return first.astimezone(timezone.utc)


def week_start(day):
    return day - timedelta(days=(day.weekday() + 1) % 7)


def summarize(tasks, events, now, zone_name, days, deadline=None):
    zone = ZoneInfo(zone_name)
    start = now.astimezone(zone).date()
    end = start + timedelta(days=days)
    left = datetime.combine(start, datetime.min.time(), zone).astimezone(timezone.utc)
    right = datetime.combine(end, datetime.min.time(), zone).astimezone(timezone.utc)
    deadline = deadline if deadline is not None else time.monotonic() + MAX_SECONDS

    def budget(count, maximum):
        if count > maximum or time.monotonic() > deadline:
            raise BriefingProblem("briefing_resource_limit")

    seen, spans = set(), []
    event_count = all_day = overdue = pending = undated = 0
    for index, event in enumerate(events, 1):
        budget(index, MAX_EVENTS)
        identity = (event.get("source", "personal"), str(event["id"]))
        if event.get("source") == "assignment" or identity in seen:
            continue
        seen.add(identity)
        if event["all_day"]:
            if event["start"] < end.isoformat() and event["end"] > start.isoformat():
                event_count += 1
                all_day += 1
        else:
            a, b = (
                datetime.fromisoformat(event[key].replace("Z", "+00:00"))
                for key in ("start", "end")
            )
            if a.utcoffset() is None or b.utcoffset() is None:
                raise BriefingProblem("briefing_unavailable")
            if a < right and b > left:
                event_count += 1
                spans.append((max(left, a), min(right, b)))
    total, until = 0, left
    for a, b in sorted(spans):
        total += max(0, (b - max(a, until)).total_seconds())
        until = max(until, b)
    for index, (due, completed) in enumerate(tasks, 1):
        budget(index, MAX_TASKS)
        if completed:
            continue
        if not due:
            undated += 1
            continue
        only_date = len(due) == 10
        instant = None if only_date else datetime.fromisoformat(due.replace("Z", "+00:00"))
        if instant is not None and instant.utcoffset() is None:
            raise BriefingProblem("briefing_unavailable")
        due_date = date.fromisoformat(due) if only_date else instant.astimezone(zone).date()
        late = due_date < start if only_date else instant < now
        overdue += late
        pending += not late and start <= due_date < end
    budget(0, MAX_TASKS)
    return {
        "events": event_count,
        "all_day": all_day,
        "minutes": round(total / 60, 2),
        "deadlines": pending,
        "overdue": overdue,
        "undated": undated,
        "range_start": start.isoformat(),
        "range_end": end.isoformat(),
    }


def cached_calendar(db, deadline, *, include_titles=False):
    return list(iter_cached_calendar(db, deadline, include_titles=include_titles))


def iter_cached_calendar(db, deadline, *, include_titles=False):
    count = 0

    def budget():
        if time.monotonic() >= deadline:
            raise BriefingProblem("briefing_resource_limit")

    def checked(event):
        nonlocal count
        budget()
        if count >= MAX_EVENTS:
            raise BriefingProblem("briefing_resource_limit")
        count += 1
        return event

    budget()
    columns = [CalendarEvent.id, CalendarEvent.start, CalendarEvent.end, CalendarEvent.all_day]
    if include_titles:
        columns.append(CalendarEvent.title)
    for row in db.execute(select(*columns).execution_options(yield_per=500)):
        budget()
        yield checked(
            {
                "id": row.id,
                "start": row.start,
                "end": row.end,
                "all_day": row.all_day,
                "source": "personal",
                **({"title": row.title} if include_titles else {}),
            }
        )
    for event in iter_calendar(db, budget):
        yield checked(event)
    for payload in db.scalars(
        select(GoogleRecord.payload)
        .join(GoogleCalendar)
        .where(GoogleRecord.kind == "visible", GoogleCalendar.selected.is_(True))
        .execution_options(yield_per=500)
    ):
        budget()
        yield checked(json.loads(payload))
    for payload in db.scalars(select(MoodleEvent.payload).execution_options(yield_per=500)):
        budget()
        yield checked(json.loads(payload))
    budget()


def stale_sources(db, now):
    stale = []
    for name, model in [("Google Calendar", GoogleConnection), ("Moodle", MoodleConnection)]:
        row = db.execute(
            select(model.state, model.last_success, model.error).where(model.id == 1)
        ).first()
        if (
            row
            and (
                row.last_success is not None
                or row.state in ("connected", "syncing", "error", "configured")
            )
            and (
                row.last_success is None
                or row.error
                or now.timestamp() - row.last_success > 1800
                or row.state not in ("connected", "syncing", "error")
            )
        ):
            stale.append(name)
    return stale


class BriefingService:
    def __init__(self, engine):
        self.engine = engine

    def _schedule(self, db):
        row = db.get(BriefingSchedule, 1)
        return ScheduleInput.model_validate(row) if row else ScheduleInput()

    def schedule(self):
        with Session(self.engine) as db:
            row = db.get(BriefingSchedule, 1)
            return {
                **self._schedule(db).model_dump(),
                "timezone": db.get(Settings, 1).timezone,
                "last_run": row.last_run if row else None,
                "last_error": row.last_error if row else None,
                "last_generated_at": db.scalar(select(func.max(ScheduledBriefing.generated_at))),
            }

    def save(self, body):
        with Session(self.engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            values = {**self._schedule(db).model_dump(), **body.model_dump(exclude_unset=True)}
            merged = ScheduleInput(**values)
            zone = ZoneInfo(db.get(Settings, 1).timezone)
            today = current_time().astimezone(zone).date()
            try:
                for index in range(371):
                    day = today + timedelta(days=index)
                    if merged.daily_enabled:
                        occurrence(day, merged.daily_time, zone)
                    if merged.weekly_enabled and day.weekday() == merged.weekly_day:
                        occurrence(day, merged.weekly_time, zone)
            except BriefingProblem:
                raise HTTPException(422, "briefing_schedule_ambiguous") from None
            db.execute(
                insert(BriefingSchedule)
                .values(id=1, **values)
                .on_conflict_do_update(index_elements=["id"], set_=values)
            )
            db.commit()
        return self.schedule()

    def generate_due(self):
        now = current_time()
        if now.utcoffset() is None:
            raise ValueError("UTC offset required")
        try:
            with Session(self.engine) as db:
                db.execute(text("BEGIN"))
                config = self._schedule(db)
                if not (config.daily_enabled or config.weekly_enabled):
                    return 0
                zone_name = db.get(Settings, 1).timezone
                zone = ZoneInfo(zone_name)
                day = now.astimezone(zone).date()
                week = week_start(day)
                slots = []
                weekly_day = week + timedelta(days=(config.weekly_day + 1) % 7)
                for enabled, kind, scheduled_day, clock, period, length in [
                    (config.daily_enabled, "daily_briefing", day, config.daily_time, day, 1),
                    (
                        config.weekly_enabled,
                        "weekly_briefing",
                        weekly_day,
                        config.weekly_time,
                        week,
                        7,
                    ),
                ]:
                    if enabled and occurrence(scheduled_day, clock, zone) <= now:
                        id = stable_id(kind, [period.isoformat(), zone_name])
                        if db.get(ScheduledBriefing, id) is None:
                            slots.append((id, kind, period.isoformat(), length))
                if not slots:
                    return 0
                deadline = time.monotonic() + MAX_SECONDS
                events = cached_calendar(db, deadline)
                stale = stale_sources(db, now)
                staged = []
                for id, kind, period, length in slots:
                    tasks = db.execute(
                        select(Task.due, Task.completed).where(actionable_tasks()).execution_options(yield_per=500)
                    )
                    payload = {
                        **summarize(tasks, events, now, zone_name, length, deadline),
                        "stale_sources": stale,
                        "generated_at": now.isoformat(),
                        "timezone": zone_name,
                    }
                    staged.append(
                        {
                            "id": id,
                            "kind": kind,
                            "period_start": period,
                            "timezone": zone_name,
                            "generated_at": now.isoformat(),
                            "payload": json.dumps(payload),
                        }
                    )
            with Session(self.engine) as db:
                db.execute(text("BEGIN IMMEDIATE"))
                if self._schedule(db) != config or db.get(Settings, 1).timezone != zone_name:
                    return 0
                if time.monotonic() > deadline:
                    raise BriefingProblem("briefing_resource_limit")
                count = 0
                for values in staged:
                    count += db.execute(
                        insert(ScheduledBriefing)
                        .values(**values)
                        .on_conflict_do_nothing(index_elements=["id"])
                    ).rowcount
                db.execute(
                    delete(ScheduledBriefing).where(
                        ScheduledBriefing.generated_at < (now - timedelta(days=90)).isoformat()
                    )
                )
                row = db.get(BriefingSchedule, 1)
                row.last_run, row.last_error = int(now.timestamp()), None
                db.flush()
                if time.monotonic() > deadline:
                    raise BriefingProblem("briefing_resource_limit")
                db.commit()
                return count
        except (BriefingProblem, ValueError) as error:
            with Session(self.engine) as db:
                row = db.get(BriefingSchedule, 1)
                if row:
                    row.last_run = int(now.timestamp())
                    row.last_error = (
                        str(error) if isinstance(error, BriefingProblem) else "briefing_unavailable"
                    )
                    db.commit()
            return 0

    def candidates(self):
        now = current_time()
        with Session(self.engine) as db:
            config = self._schedule(db)
            zone_name = db.get(Settings, 1).timezone
            today = now.astimezone(ZoneInfo(zone_name)).date()
            rows = db.scalars(
                select(ScheduledBriefing).where(
                    ScheduledBriefing.timezone == zone_name,
                    ScheduledBriefing.period_start >= week_start(today).isoformat(),
                )
            )
            return [
                {
                    "id": row.id,
                    "kind": row.kind,
                    "title": row.kind,
                    "target": "dashboard",
                    "source_ids": [],
                    "priority": -1,
                    "order": row.generated_at,
                    "briefing": json.loads(row.payload),
                }
                for row in rows
                if (
                    row.kind == "daily_briefing"
                    and config.daily_enabled
                    and row.period_start == today.isoformat()
                )
                or (
                    row.kind == "weekly_briefing"
                    and config.weekly_enabled
                    and row.period_start == week_start(today).isoformat()
                )
            ]


def briefing_router(service, authenticated):
    router = APIRouter(prefix="/briefings", dependencies=[Depends(authenticated)])

    @router.get("/schedule")
    def schedule():
        return service.schedule()

    @router.put("/schedule")
    def save(body: ScheduleInput):
        return service.save(body)

    @router.post("/check")
    def check():
        return {"generated": service.generate_due(), "schedule": service.schedule()}

    return router
