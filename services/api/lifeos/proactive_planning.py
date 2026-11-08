"""One read-only owned suggestion; only existing reviewed planning writes events."""

import json
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .academic import begin_academic_write
from .academic_models import AcademicItem, Course, Term
from .account_planning import AccountPlanning, block_signature, without_replacement
from .account_snapshot import AccountSnapshot
from .assistant import interval
from .assistant_models import AssistantProposal
from .models import AccountNoticeState, AccountPreference, AccountProvider, CalendarEvent, Task
from .planning_preferences import DEFAULTS
from .recommendations import stable_id
from .secretary_preferences import secretary_preferences
from .task_planning import PlanningInput, choose_slot, due_limit, signature
from .task_planning_models import TaskTimeBlock


def source_state(db, owner, now):
    rows = list(
        db.scalars(
            select(AccountProvider).where(
                AccountProvider.account_id == owner,
                AccountProvider.provider.in_(["google", "moodle", "braude"]),
                AccountProvider.credentials.is_not(None),
            )
        )
    )
    stale = [
        row.provider
        for row in rows
        if row.error or row.last_success is None or row.last_success < now.timestamp() - 1800
    ]
    return sorted(stale), sorted([[row.provider, row.revision] for row in rows])


def verify_proactive_guard(db, owner, guard, now):
    stale, sources = source_state(db, owner, now)
    pref = db.get(AccountPreference, (owner, "planning"))
    _, secretary_revision = secretary_preferences(db, owner)
    settings = db.get(AccountPreference, (owner, "settings"))
    zone = (
        json.loads(settings.payload).get("timezone", "Asia/Jerusalem")
        if settings
        else "Asia/Jerusalem"
    )
    if (
        stale
        or sources != guard["sources"]
        or (pref.revision if pref else 0) != guard["preferences_revision"]
        or zone != guard["timezone"]
        or ("secretary_revision" in guard and secretary_revision != guard["secretary_revision"])
    ):
        raise ValueError("Planning inputs changed; refresh suggestion")


class ProactivePlanning(AccountSnapshot):
    def suggestion(self, owner, *, now=None):
        now = now or datetime.now(timezone.utc)
        deadline = time.monotonic() + 10
        with Session(self.engine) as db:
            db.execute(text("BEGIN"))
            self.authorize(db, owner)
            controls, controls_revision = secretary_preferences(db, owner)
            if not controls.proactive_enabled:
                return {"suggestion": None, "reason": "paused", "stale_sources": []}
            stale, sources = source_state(db, owner, now)
            if stale:
                return {"suggestion": None, "reason": "stale_sources", "stale_sources": stale}
            snapshot = self.build(owner, db=db)
            pref = db.get(AccountPreference, (owner, "planning"))
            values = {**DEFAULTS, **(json.loads(pref.payload) if pref else {})}
            used = values["enabled"]
            zone = ZoneInfo(snapshot["settings"]["timezone"])
            today = now.astimezone(zone).date()
            eligible = [task for task in snapshot["tasks"] if not task["completed"] and task["due"]]
            eligible.sort(key=lambda task: (task["due"], task["priority"] != "high", task["id"]))
            academic = {
                task_id: (kind, name)
                for task_id, kind, name in db.execute(
                    select(AcademicItem.task_id, AcademicItem.kind, Course.name)
                    .join(Course, Course.id == AcademicItem.course_id)
                    .join(Term, Term.id == Course.term_id)
                    .join(Task, Task.id == AcademicItem.task_id)
                    .where(Term.account_id == owner, Task.account_id == owner)
                )
            }
            linked = {
                task_id: event
                for task_id, event in db.execute(
                    select(TaskTimeBlock.task_id, CalendarEvent)
                    .join(Task, Task.id == TaskTimeBlock.task_id)
                    .join(CalendarEvent, CalendarEvent.id == TaskTimeBlock.event_id)
                    .where(Task.account_id == owner, CalendarEvent.account_id == owner)
                )
                if datetime.fromisoformat(event.end.replace("Z", "+00:00")) > now
            }
            searched = 0
            for task in eligible:
                due = task["due"]
                due_day = (
                    datetime.fromisoformat(due.replace("Z", "+00:00")).astimezone(zone).date()
                    if len(due) != 10
                    else datetime.fromisoformat(due).date()
                )
                if academic.get(task["id"], ("", ""))[
                    0
                ] == "exam" or not today <= due_day <= today + timedelta(days=7):
                    continue
                replacement = None
                reason = "unplanned_deadline"
                duration = values["duration"] if used else 30
                existing = linked.get(task["id"])
                if existing:
                    begin, finish = interval(
                        {"start": existing.start, "end": existing.end, "all_day": existing.all_day},
                        zone,
                    )
                    if existing.all_day or begin <= now:
                        continue
                    replacement = {
                        "id": existing.id,
                        "signature": block_signature(existing),
                        "start": existing.start,
                        "end": existing.end,
                    }
                    cutoff, overdue = due_limit(due, now, zone)
                    if cutoff and finish > cutoff:
                        reason = "after_deadline"
                    elif any(
                        event.get("source") != "assignment"
                        and begin < interval(event, zone)[1]
                        and finish > interval(event, zone)[0]
                        for event in without_replacement(snapshot["events"], replacement)
                    ):
                        reason = "calendar_conflict"
                    else:
                        continue
                    minutes = (finish - begin).total_seconds() / 60
                    if not minutes.is_integer() or not 5 <= minutes <= 240 or minutes % 5:
                        continue
                    duration = int(minutes)
                searched += 1
                if searched > 20:
                    break
                body = PlanningInput(
                    task_id=task["id"],
                    day=today,
                    days=values["days"] if used else 7,
                    duration=duration,
                    window_start=values["window_start"] if used else "08:00",
                    window_end=values["window_end"] if used else "20:00",
                    weekdays=values["weekdays"] if used else list(range(1, 8)),
                    daily_limit_minutes=values["daily_limit_minutes"] if used else None,
                )
                slot, overdue = choose_slot(
                    body,
                    due,
                    without_replacement(snapshot["events"], replacement),
                    now,
                    zone,
                    deadline,
                )
                if not slot or overdue:
                    continue
                request = body.model_dump(mode="json")
                task_signature = signature(SimpleNamespace(**task))
                snooze_key = stable_id("planning_snooze", [task_signature, reason, replacement])
                receipt = db.get(AccountNoticeState, (owner, snooze_key))
                if receipt and (receipt.recommendation_until or 0) > now.timestamp():
                    continue
                guard = {
                    "sources": sources,
                    "preferences_revision": pref.revision if pref else 0,
                    "timezone": zone.key,
                    "secretary_revision": controls_revision,
                }
                start, end = [instant.isoformat() for instant in slot]
                id = stable_id(
                    "proactive_plan", [task_signature, start, end, request, guard, replacement]
                )
                return {
                    "suggestion": {
                        "id": id,
                        "task_id": task["id"],
                        "task_signature": task_signature,
                        "title": task["title"],
                        "course_name": academic.get(task["id"], ("", ""))[1],
                        "due": due,
                        "start": start,
                        "end": end,
                        "duration": body.duration,
                        "preferences_used": used,
                        "replacement": replacement,
                        "reason": reason,
                        "snooze_key": snooze_key,
                        "snooze_minutes": controls.suggestion_snooze_minutes,
                        "request": request,
                        "guard": guard,
                    },
                    "stale_sources": [],
                }
        return {"suggestion": None, "reason": "no_suggestion", "stale_sources": []}

    def dismiss(self, owner, id, *, now=None):
        now = now or datetime.now(timezone.utc)
        current = self.suggestion(owner, now=now)["suggestion"]
        if current is None or current["id"] != id:
            raise ValueError("Suggestion changed; refresh")
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, owner)
            row = db.get(AccountNoticeState, (owner, current["snooze_key"]))
            if row is None:
                row = AccountNoticeState(account_id=owner, id=current["snooze_key"])
                db.add(row)
            until = int(now.timestamp()) + current["snooze_minutes"] * 60
            row.recommendation_until = until
            row.updated_at = int(now.timestamp())
            db.commit()
        return {"snoozed_until": until}

    def propose(self, owner, token, suggestion_id, *, now=None):
        now = now or datetime.now(timezone.utc)
        current = self.suggestion(owner, now=now)["suggestion"]
        if current is None or current["id"] != suggestion_id:
            raise ValueError("Suggestion changed; refresh")
        result = AccountPlanning(self.engine).propose(
            owner, token, current["request"], now=now, replacement=current["replacement"]
        )
        proposal = result.get("proposal")
        if not proposal:
            raise ValueError("Slot no longer available")
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, owner)
            stored = db.get(AssistantProposal, proposal["id"])
            if stored is None:
                raise ValueError("Proposal no longer available")
            payload = json.loads(stored.payload)
            try:
                verify_proactive_guard(db, owner, current["guard"], now)
                if payload["signature"] != current["task_signature"]:
                    raise ValueError("Task changed; refresh")
                if any(
                    datetime.fromisoformat(proposal["record"][key].replace("Z", "+00:00"))
                    != datetime.fromisoformat(current[key])
                    for key in ("start", "end")
                ):
                    raise ValueError("Slot changed; refresh")
            except ValueError:
                db.delete(stored)
                db.commit()
                raise
            payload["proactive_guard"] = current["guard"]
            stored.payload = json.dumps(payload)
            db.commit()
        from .account_requests import AccountRequests

        try:
            result["request_tracking_warning"] = not AccountRequests(self.engine).link_task_plan(
                owner, current["task_id"], proposal["id"]
            )
        except Exception:
            result["request_tracking_warning"] = True
        return result
