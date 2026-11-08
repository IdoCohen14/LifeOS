"""Quiet deterministic recommendations. No inference, notifications or record mutations."""

import hashlib
import json
import time
from contextlib import closing, nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from .models import Settings, Task
from .recommendation_models import RecommendationDismissal
from .task_scope import actionable_tasks


def current_time():
    return datetime.now(timezone.utc)


def stable_id(kind, values):
    return hashlib.sha256(
        json.dumps([kind, values], sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class RecommendationService:
    def __init__(self, engine, calendar, google, moodle, *, deadline=None):
        self.engine, self.calendar, self.google, self.moodle = engine, calendar, google, moodle
        self.deadline = deadline

    def cached_calendar(self, deadline):
        # Lazy import: briefings shares stable_id with this module.
        from .briefings import BriefingProblem, iter_cached_calendar

        try:
            with Session(self.engine) as db:
                db.execute(text("BEGIN"))
                yield from iter_cached_calendar(db, deadline, include_titles=True)
        except BriefingProblem:
            raise HTTPException(503, "recommendation_resource_limit") from None

    def candidates(self, *, snapshot=None):
        deadline = min(
            time.monotonic() + 10, self.deadline if self.deadline is not None else float("inf")
        )

        def budget(count, maximum):
            if count > maximum or time.monotonic() >= deadline:
                raise HTTPException(503, "recommendation_resource_limit")

        now = current_time()
        until = now + timedelta(hours=48)
        items = []
        with Session(self.engine) as db:
            zone = ZoneInfo(
                snapshot["settings"]["timezone"]
                if snapshot is not None
                else db.get(Settings, 1).timezone
            )
            today = now.astimezone(zone).date()
            for index, task in enumerate(
                (
                    SimpleNamespace(**row)
                    for row in snapshot["tasks"]
                    if not row["completed"] and row["due"] is not None and row.get("academic_kind") != "exam"
                )
                if snapshot is not None
                else db.scalars(
                    select(Task)
                    .where(Task.completed.is_(False), Task.due.is_not(None), actionable_tasks())
                    .execution_options(yield_per=200)
                ),
                1,
            ):
                budget(index, 100000)
                date_only = len(task.due) == 10
                if date_only:
                    due_day = datetime.fromisoformat(task.due).date()
                    overdue = due_day < today
                    if not overdue and due_day > until.astimezone(zone).date():
                        continue
                    order = task.due
                else:
                    due = datetime.fromisoformat(task.due.replace("Z", "+00:00"))
                    overdue = due < now
                    if due > until:
                        continue
                    order = due.astimezone(zone).isoformat()
                kind = "overdue" if overdue else "due_soon"
                items.append(
                    {
                        "id": stable_id(
                            kind, [task.id, task.title, task.due, task.priority, zone.key]
                        ),
                        "kind": kind,
                        "title": task.title,
                        "due": task.due,
                        "target": "tasks",
                        "source_ids": [task.id],
                        "priority": 1
                        if overdue and task.priority == "high"
                        else 2
                        if overdue
                        else 3,
                        "order": order,
                    }
                )
        unique = {}
        calendar = (
            snapshot["events"]
            if snapshot is not None
            else self.calendar()
            if self.calendar is not None
            else self.cached_calendar(deadline)
        )
        with (
            closing(calendar)
            if snapshot is None and self.calendar is None
            else nullcontext(calendar) as records
        ):
            for index, event in enumerate(records, 1):
                budget(index, 20000)
                if event.get("all_day") or event.get("source") == "assignment":
                    continue
                start = datetime.fromisoformat(event["start"].replace("Z", "+00:00")).astimezone(
                    timezone.utc
                )
                end = datetime.fromisoformat(event["end"].replace("Z", "+00:00")).astimezone(
                    timezone.utc
                )
                if end <= now or start >= until:
                    continue
                if (
                    event.get("source") in ("google", "moodle")
                    and (end - start).total_seconds() <= 60
                ):
                    continue
                signature = (
                    " ".join(event["title"].casefold().split()),
                    start.isoformat(),
                    end.isoformat(),
                )
                group = unique.setdefault(signature, (start, end, event, signature, set()))
                group[4].add((event.get("source", "personal"), str(event.get("id", signature))))
        events = sorted(unique.values(), key=lambda item: (item[0], item[3]))
        active, conflicts = [], 0
        for start, end, event, signature, identities in events:
            active = [old for old in active if old[1] > start]
            for previous in active:
                other = previous[2]
                participants = sorted(
                    [(signature, sorted(identities)), (previous[3], sorted(previous[4]))],
                    key=lambda part: part[0],
                )
                items.append(
                    {
                        "id": stable_id("conflict", participants),
                        "kind": "conflict",
                        "title": event["title"],
                        "other_title": other["title"],
                        "start": max(start, previous[0]).isoformat(),
                        "end": min(end, previous[1]).isoformat(),
                        "target": "calendar",
                        "source_ids": [event.get("id"), other.get("id")],
                        "priority": 0,
                        "order": start.isoformat(),
                    }
                )
                conflicts += 1
                if conflicts >= 20:
                    break
            if conflicts >= 20:
                break
            active.append((start, end, event, signature, identities))
        budget(0, 20000)
        return sorted(
            items, key=lambda item: (item["priority"], item["order"], item["id"])
        ), conflicts >= 20

    def feed(self):
        candidates, limited = self.candidates()
        with Session(self.engine) as db:
            hidden = set(
                db.scalars(
                    select(RecommendationDismissal.id).where(
                        RecommendationDismissal.expires > current_time().timestamp()
                    )
                )
            )
        visible = [item for item in candidates if item["id"] not in hidden]
        stale = []
        for name, provider in [("Google Calendar", self.google), ("Moodle", self.moodle)]:
            status = provider.status()
            if status.get("stale") or status.get("error"):
                stale.append(name)
        return {
            "items": visible[:5],
            "truncated": limited or len(visible) > 5,
            "stale_sources": stale,
        }

    def dismiss(self, id):
        candidates, _ = self.candidates()
        if id not in {item["id"] for item in candidates}:
            raise HTTPException(404, "recommendation_changed")
        now = int(current_time().timestamp())
        with Session(self.engine) as db:
            db.execute(
                delete(RecommendationDismissal).where(RecommendationDismissal.expires <= now)
            )
            db.execute(
                insert(RecommendationDismissal)
                .values(id=id, expires=now + 86400)
                .on_conflict_do_nothing(index_elements=["id"])
            )
            db.commit()
        return self.feed()


class DismissInput(BaseModel):
    id: str = Field(pattern=r"^[0-9a-f]{64}$")


def recommendation_router(service, authenticated):
    router = APIRouter(prefix="/recommendations", dependencies=[Depends(authenticated)])

    @router.get("")
    def feed():
        return service.feed()

    @router.post("/dismiss")
    def dismiss(body: DismissInput):
        return service.dismiss(body.id)

    return router
