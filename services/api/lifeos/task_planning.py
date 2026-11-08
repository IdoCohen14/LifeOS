"""Bounded cached-calendar task proposals. Only explicit confirmation creates an event."""

import json
import math
import time
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from .assistant import day_boundary, interval, local_instant, unambiguous_instant
from .assistant_models import AssistantProposal
from .briefings import CLOCK, MAX_SECONDS, BriefingProblem, cached_calendar, stale_sources
from .daily_capacity import scheduled_minutes
from .models import CalendarEvent, LoginSession, Settings, Task
from .planning_preferences import Weekdays, normalize_weekdays
from .recommendations import stable_id
from .schemas import EventInput
from .task_planning_models import TaskTimeBlock
from .task_scope import is_actionable_task


def current_time():
    return datetime.now(timezone.utc)


class PlanningInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    day: date
    days: int = Field(default=1, ge=1, le=7)
    duration: int = Field(default=30, ge=5, le=240, multiple_of=5)
    window_start: str = Field(default="08:00", pattern=CLOCK)
    window_end: str = Field(default="20:00", pattern=CLOCK)
    allow_after_due: bool = False
    daily_limit_minutes: int | None = Field(default=None, ge=15, le=1440, multiple_of=15)
    weekdays: Weekdays = Field(default_factory=lambda: list(range(1, 8)))

    @field_validator("weekdays")
    @classmethod
    def weekdays_valid(cls, value):
        return normalize_weekdays(value)

    @model_validator(mode="after")
    def window(self):
        if self.window_start >= self.window_end:
            raise ValueError("invalid_window")
        return self


def signature(task):
    return stable_id("task_plan", [task.id, task.title, task.due, task.priority, task.completed])


def due_limit(due, now, zone):
    if not due:
        return None, False
    if len(due) == 10:
        day = date.fromisoformat(due)
        late = day < now.astimezone(zone).date()
        return (
            None
            if late or day == date.max
            else day_boundary((day + timedelta(days=1)).isoformat(), zone)
        ), late
    instant = datetime.fromisoformat(due.replace("Z", "+00:00"))
    late = instant < now
    return None if late else instant, late


def windows(body, zone):
    try:
        return [
            (
                local_instant((body.day + timedelta(days=i)).isoformat(), body.window_start, zone),
                local_instant((body.day + timedelta(days=i)).isoformat(), body.window_end, zone),
            )
            for i in range(body.days)
            if (body.day + timedelta(days=i)).isoweekday() in body.weekdays
        ]
    except (ValueError, TypeError):
        raise HTTPException(422, "planning_time_ambiguous") from None


def existing_block(db, task_id, now, zone):
    link = db.get(TaskTimeBlock, task_id)
    event = db.get(CalendarEvent, link.event_id) if link else None
    if (
        event
        and interval({"start": event.start, "end": event.end, "all_day": event.all_day}, zone)[1]
        > now
    ):
        return {
            "id": event.id,
            "title": event.title,
            "start": event.start,
            "end": event.end,
            "all_day": event.all_day,
        }
    return None


def check_budget(deadline):
    if time.monotonic() >= deadline:
        raise HTTPException(503, "planning_resource_limit")


def choose_slot(body, due, events, now, zone, deadline):
    spans = windows(body, zone)
    cutoff, overdue = due_limit(due, now, zone)
    if not spans:
        check_budget(deadline)
        return None, overdue
    busy = []
    timed = []
    for event in events:
        check_budget(deadline)
        if event.get("source") == "assignment":
            continue
        begin, end = interval(event, zone)
        if not event.get("all_day"):
            timed.append((begin, end))
        if begin < spans[-1][1] and end > spans[0][0]:
            busy.append((begin, end))
    merged = []
    for begin, end in sorted(busy):
        if merged and begin <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((begin, end))
    duration = timedelta(minutes=body.duration)
    for left, right in spans:
        check_budget(deadline)
        if (
            body.daily_limit_minutes is not None
            and scheduled_minutes(
                timed, left.astimezone(zone).date(), zone, lambda: check_budget(deadline)
            )
            + body.duration
            > body.daily_limit_minutes
        ):
            continue
        if cutoff and not body.allow_after_due:
            right = min(right, cutoff)
        anchor = day_boundary(left.astimezone(zone).date().isoformat(), zone)
        cursor = anchor + timedelta(
            seconds=900 * math.ceil((max(left, now) - anchor).total_seconds() / 900)
        )
        index = 0
        while cursor + duration <= right:
            check_budget(deadline)
            finish = cursor + duration
            if not unambiguous_instant(cursor, zone) or not unambiguous_instant(finish, zone):
                cursor += timedelta(minutes=15)
                continue
            while index < len(merged) and merged[index][1] <= cursor:
                check_budget(deadline)
                index += 1
            if index < len(merged) and merged[index][0] < finish:
                if merged[index][1] >= right:
                    break
                cursor = anchor + timedelta(
                    seconds=900
                    * math.ceil((max(left, merged[index][1]) - anchor).total_seconds() / 900)
                )
                continue
            check_budget(deadline)
            return (cursor, finish), overdue
    check_budget(deadline)
    return None, overdue


class TaskPlanningService:
    def __init__(self, engine):
        self.engine = engine

    def propose(self, body, session_hash):
        now = current_time().astimezone(timezone.utc)
        deadline = time.monotonic() + MAX_SECONDS
        with Session(self.engine) as db:
            db.execute(text("BEGIN"))
            task = db.get(Task, body.task_id)
            if not is_actionable_task(task) or task.completed:
                raise HTTPException(409, "planning_source_changed")
            settings = db.get(Settings, 1)
            zone_name, language = settings.timezone, settings.language
            zone = ZoneInfo(zone_name)
            today = now.astimezone(zone).date()
            if not today <= body.day <= today + timedelta(days=30):
                raise HTTPException(422, "planning_day_range")
            windows(body, zone)
            existing = existing_block(db, task.id, now, zone)
            if existing:
                return {"proposal": None, "existing": existing}
            original = signature(task)
            try:
                events = cached_calendar(db, deadline)
                slot, overdue = choose_slot(body, task.due, events, now, zone, deadline)
            except BriefingProblem:
                raise HTTPException(503, "planning_resource_limit") from None
            if slot is None:
                return {"proposal": None, "existing": None, "reason": "no_slot"}
            stale = stale_sources(db, now)
            payload = EventInput(
                title=task.title,
                notes="משבצת זמן למשימה ב־LifeOS; המשימה נשארת פתוחה."
                if language == "he"
                else "Time allocated to a LifeOS task; the task stays open.",
                start=slot[0].isoformat(),
                end=slot[1].isoformat(),
            ).model_dump()
        id = str(uuid4())
        with Session(self.engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            session = db.get(LoginSession, session_hash)
            if not session or session.expires <= time.time():
                raise HTTPException(401, "session_expired")
            task = db.get(Task, body.task_id)
            if (
                task is None
                or signature(task) != original
                or db.get(Settings, 1).timezone != zone_name
            ):
                raise HTTPException(409, "planning_source_changed")
            if existing_block(db, task.id, now, zone):
                raise HTTPException(409, "task_already_planned")
            db.execute(
                delete(AssistantProposal).where(
                    AssistantProposal.expires < time.time(),
                    AssistantProposal.confirmed_id.is_(None),
                )
            )
            pending = db.scalar(
                select(func.count())
                .select_from(AssistantProposal)
                .where(
                    AssistantProposal.session_hash == session_hash,
                    AssistantProposal.confirmed_id.is_(None),
                )
            )
            if pending >= 20:
                raise HTTPException(429, "planning_proposal_limit")
            check_budget(deadline)
            db.add(
                AssistantProposal(
                    id=id,
                    session_hash=session_hash,
                    kind="event",
                    payload=json.dumps(
                        {
                            "record": payload,
                            "planning_task": {
                                "task_id": task.id,
                                "signature": original,
                                "timezone": zone_name,
                                "request": body.model_dump(mode="json"),
                            },
                        }
                    ),
                    expires=int(time.time()) + 900,
                )
            )
            db.commit()
        return {
            "proposal": {"id": id, "kind": "event", "payload": payload},
            "existing": None,
            "overdue": overdue,
            "deadline_ignored": body.allow_after_due,
            **(
                {"daily_limit_minutes": body.daily_limit_minutes}
                if body.daily_limit_minutes is not None
                else {}
            ),
            "stale_sources": stale,
        }

    def cancel(self, id, session_hash):
        with Session(self.engine) as db:
            db.execute(text("BEGIN IMMEDIATE"))
            proposal = db.get(AssistantProposal, id)
            if (
                not proposal
                or proposal.session_hash != session_hash
                or proposal.confirmed_id
                or "planning_task" not in json.loads(proposal.payload)
            ):
                raise HTTPException(404, "proposal_expired")
            db.delete(proposal)
            db.commit()


def verify_planning_proposal(db, stored):
    metadata = stored["planning_task"]
    body = PlanningInput.model_validate(metadata["request"])
    task = db.get(Task, metadata["task_id"])
    zone_name = db.get(Settings, 1).timezone
    if (
        not is_actionable_task(task)
        or task.completed
        or signature(task) != metadata["signature"]
        or zone_name != metadata["timezone"]
    ):
        raise HTTPException(409, "planning_source_changed")
    zone = ZoneInfo(zone_name)
    now = current_time().astimezone(timezone.utc)
    begin, finish = interval(stored["record"], zone)
    if not unambiguous_instant(begin, zone) or not unambiguous_instant(finish, zone):
        raise HTTPException(409, "schedule_changed")
    if begin < now or existing_block(db, task.id, now, zone):
        raise HTTPException(409, "schedule_changed")
    cutoff, _ = due_limit(task.due, now, zone)
    if cutoff and not body.allow_after_due and finish > cutoff:
        raise HTTPException(409, "planning_source_changed")
    if not any(left <= begin and finish <= right for left, right in windows(body, zone)):
        raise HTTPException(409, "schedule_changed")
    deadline = time.monotonic() + MAX_SECONDS
    try:
        timed = []
        for event in cached_calendar(db, deadline):
            check_budget(deadline)
            if event.get("source") == "assignment":
                continue
            start, end = interval(event, zone)
            if not event.get("all_day"):
                timed.append((start, end))
            if begin < end and finish > start:
                raise HTTPException(409, "schedule_changed")
        if (
            body.daily_limit_minutes is not None
            and scheduled_minutes(
                timed, begin.astimezone(zone).date(), zone, lambda: check_budget(deadline)
            )
            + (finish - begin).total_seconds() / 60
            > body.daily_limit_minutes
        ):
            raise HTTPException(409, "schedule_changed")
    except BriefingProblem:
        raise HTTPException(503, "planning_resource_limit") from None
    return deadline


def final_planning_check(db, stored, deadline, session_hash, proposal_id):
    db.flush()
    check_budget(deadline)
    session = db.get(LoginSession, session_hash)
    proposal = db.get(AssistantProposal, proposal_id)
    if not session or session.expires <= time.time():
        raise HTTPException(401, "session_expired")
    if not proposal or proposal.expires <= time.time():
        raise HTTPException(404, "proposal_expired")
    begin = datetime.fromisoformat(stored["record"]["start"].replace("Z", "+00:00"))
    if begin < current_time().astimezone(timezone.utc):
        raise HTTPException(409, "schedule_changed")


def save_plan_link(db, stored, event_id):
    task_id = stored["planning_task"]["task_id"]
    db.flush()
    db.execute(
        insert(TaskTimeBlock)
        .values(task_id=task_id, event_id=event_id)
        .on_conflict_do_update(index_elements=["task_id"], set_={"event_id": event_id})
    )


def planning_router(service, authenticated):
    router = APIRouter(prefix="/planning", dependencies=[Depends(authenticated)])

    @router.post("/propose")
    def propose(body: PlanningInput, session=Depends(authenticated)):
        return service.propose(body, session.token_hash)

    @router.delete("/proposals/{id}", status_code=204)
    def cancel(id: str, session=Depends(authenticated)):
        service.cancel(id, session.token_hash)

    return router
