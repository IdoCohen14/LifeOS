"""Read-only in-app candidates with explicitly persisted local acknowledgements."""

import time
from datetime import datetime, timezone
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, or_, select, text
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from .briefings import BriefingService
from .calendar_notices import upcoming_events
from .mail_notifications import mail_candidates
from .models import Settings
from .moodle_changes import change_candidates
from .notification_models import NotificationAction, NotificationPreferences, NotificationRead


def current_time():
    return datetime.now(timezone.utc)


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    enabled: bool = True
    tasks: bool = True
    conflicts: bool = True
    briefings: bool = True
    mail: bool = False
    events: bool = False
    quiet_enabled: bool = True
    quiet_start: str = Field(default="22:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    quiet_end: str = Field(default="07:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class ReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]] = Field(min_length=1, max_length=20)


class ActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: Literal["dismiss", "snooze", "restore"]
    minutes: Literal[15, 60, 1440] | None = None

    @model_validator(mode="after")
    def duration(self):
        if (self.action == "snooze") != (self.minutes is not None):
            raise ValueError("snooze_requires_duration")
        return self


class NotificationService:
    def __init__(self, recommendations):
        self.recommendations = recommendations
        self.engine = recommendations.engine
        self.briefings = BriefingService(self.engine)

    def candidates(self):
        items, limited = self.recommendations.candidates()
        with Session(self.engine) as db:
            prefs = self.preferences(db)
        mail = mail_candidates(self.engine) if prefs.enabled and prefs.mail else []
        events = (
            (
                upcoming_events(self.engine, current_time())
                + change_candidates(self.engine, current_time())
            )
            if prefs.enabled and prefs.events
            else []
        )
        return sorted(
            items + self.briefings.candidates() + mail + events,
            key=lambda item: (item["priority"], item["order"], item["id"]),
        ), limited

    def preferences(self, db):
        row = db.get(NotificationPreferences, 1)
        return Preferences.model_validate(row) if row else Preferences()

    def feed(self):
        deadline = time.monotonic() + 10

        def check_budget():
            if time.monotonic() >= deadline:
                raise HTTPException(503, "notifications_resource_limit")

        candidates, limited = self.candidates()
        check_budget()
        with Session(self.engine) as db:
            db.execute(text("BEGIN"))
            prefs = self.preferences(db)
            zone = ZoneInfo(db.get(Settings, 1).timezone)
            reads = set()
            actions = {}
            ids = [item["id"] for item in candidates]
            for offset in range(0, len(ids), 500):
                check_budget()
                batch = ids[offset : offset + 500]
                reads.update(
                    db.scalars(select(NotificationRead.id).where(NotificationRead.id.in_(batch)))
                )
                actions.update(
                    {
                        row.id: (row.dismissed, row.snoozed_until)
                        for row in db.scalars(
                            select(NotificationAction).where(NotificationAction.id.in_(batch))
                        )
                    }
                )
                check_budget()
        local = current_time().astimezone(zone).strftime("%H:%M")
        start, end = prefs.quiet_start, prefs.quiet_end
        quiet = prefs.quiet_enabled and (
            start == end or (start <= local < end if start < end else local >= start or local < end)
        )
        now = int(current_time().timestamp())
        selected = [
            {
                **item,
                "read": item["id"] in reads,
                "dismissed": actions.get(item["id"], (False, None))[0],
                "snoozed_until": actions.get(item["id"], (False, None))[1],
            }
            for item in candidates
            if prefs.enabled
            and (
                prefs.briefings
                if item["kind"].endswith("_briefing")
                else prefs.conflicts
                if item["kind"] == "conflict"
                else prefs.events
                if item["kind"] in ("upcoming_event", "moodle_update")
                else prefs.mail
                if item["kind"] == "new_mail"
                else prefs.tasks
            )
        ]
        hidden = [
            item for item in selected if item["dismissed"] or (item["snoozed_until"] or 0) > now
        ]
        selected = [
            item
            for item in selected
            if not item["dismissed"] and (item["snoozed_until"] or 0) <= now
        ]
        selected.sort(key=lambda item: item["read"])
        stale = []
        for name, provider in [
            ("Google Calendar", self.recommendations.google),
            ("Moodle", self.recommendations.moodle),
        ]:
            status = provider.status()
            if (status.get("connected") or status.get("last_success") is not None) and (
                not status.get("connected")
                or not status.get("last_success")
                or status.get("stale")
                or status.get("error")
            ):
                stale.append(name)
        check_budget()
        return {
            "items": selected[:20],
            "hidden": hidden[:20],
            "hidden_total": len(hidden),
            "hidden_truncated": len(hidden) > 20,
            "unread": sum(not item["read"] for item in selected),
            "truncated": len(selected) > 20,
            "conflicts_limited": limited,
            "quiet": quiet,
            "preferences": prefs.model_dump(),
            "stale_sources": stale,
        }

    def save_preferences(self, body):
        with Session(self.engine) as db:
            patch = body.model_dump(exclude_unset=True)
            # Insert defaults; concurrent partial writes update only their supplied fields.
            statement = insert(NotificationPreferences).values(
                id=1, **{**Preferences().model_dump(), **patch}
            )
            db.execute(
                statement.on_conflict_do_update(index_elements=["id"], set_=patch)
                if patch
                else statement.on_conflict_do_nothing(index_elements=["id"])
            )
            db.commit()
        return self.feed()

    def mark_read(self, ids):
        candidates, _ = self.candidates()
        current_ids = {item["id"] for item in candidates}
        if not set(ids) <= current_ids:
            raise HTTPException(409, "notifications_changed")
        now = int(current_time().timestamp())
        with Session(self.engine) as db:
            # Serialize eligibility with snooze/dismiss writes across API threads/tabs.
            db.execute(text("BEGIN IMMEDIATE"))
            hidden = db.scalar(
                select(NotificationAction.id)
                .where(
                    NotificationAction.id.in_(ids),
                    or_(
                        NotificationAction.dismissed.is_(True),
                        NotificationAction.snoozed_until > now,
                    ),
                )
                .limit(1)
            )
            if hidden:
                raise HTTPException(409, "notifications_changed")
            # Retain active acknowledgements indefinitely; prune only aged, resolved versions.
            old = list(
                db.scalars(
                    select(NotificationRead.id).where(NotificationRead.read_at < now - 30 * 86400)
                )
            )
            obsolete = [id for id in old if id not in current_ids]
            for offset in range(0, len(obsolete), 500):
                db.execute(
                    delete(NotificationRead).where(
                        NotificationRead.id.in_(obsolete[offset : offset + 500])
                    )
                )
            for id in set(ids):
                db.execute(
                    insert(NotificationRead)
                    .values(id=id, read_at=now)
                    .on_conflict_do_nothing(index_elements=["id"])
                )
            db.commit()
        return self.feed()

    def action(self, body):
        candidates, _ = self.candidates()
        current_ids = {item["id"] for item in candidates}
        if body.id not in current_ids:
            raise HTTPException(409, "notifications_changed")
        now = int(current_time().timestamp())
        values = {
            "dismissed": body.action == "dismiss",
            "snoozed_until": now + body.minutes * 60 if body.action == "snooze" else None,
            "updated_at": now,
        }
        with Session(self.engine) as db:
            old = list(
                db.scalars(
                    select(NotificationAction.id).where(
                        NotificationAction.updated_at < now - 30 * 86400
                    )
                )
            )
            obsolete = [id for id in old if id not in current_ids]
            for offset in range(0, len(obsolete), 500):
                db.execute(
                    delete(NotificationAction).where(
                        NotificationAction.id.in_(obsolete[offset : offset + 500])
                    )
                )
            if body.action == "restore":
                db.execute(delete(NotificationAction).where(NotificationAction.id == body.id))
            else:
                db.execute(
                    insert(NotificationAction)
                    .values(id=body.id, **values)
                    .on_conflict_do_update(index_elements=["id"], set_=values)
                )
            if body.action == "snooze":
                db.execute(delete(NotificationRead).where(NotificationRead.id == body.id))
            db.commit()
        return self.feed()


def notification_router(service, authenticated):
    router = APIRouter(prefix="/notifications", dependencies=[Depends(authenticated)])

    @router.get("")
    def feed():
        return service.feed()

    @router.put("/preferences")
    def preferences(body: Preferences):
        return service.save_preferences(body)

    @router.post("/read")
    def read(body: ReadInput):
        return service.mark_read(body.ids)

    @router.post("/action")
    def action(body: ActionInput):
        return service.action(body)

    return router
