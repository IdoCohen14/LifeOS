"""Account/session-bound explicit task planning using owned calendar snapshots."""

import json
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .academic import begin_academic_write
from .account_snapshot import AccountSnapshot
from .accounts import require_account_session
from .assistant_models import AssistantProposal
from .models import CalendarEvent, Task
from .recommendations import stable_id
from .schemas import EventInput
from .task_planning import PlanningInput, choose_slot, signature
from .task_planning_models import TaskTimeBlock
from .task_scope import actionable_tasks


def block_signature(event):
    return stable_id(
        "local_work_block",
        [getattr(event, key) for key in ("id", "title", "notes", "start", "end", "all_day")],
    )


def verify_replacement(event, replacement, now):
    if (
        event is None
        or event.id != replacement["id"]
        or block_signature(event) != replacement["signature"]
        or event.all_day
        or datetime.fromisoformat(event.start.replace("Z", "+00:00")) <= now
    ):
        raise ValueError("Work block changed; refresh")


def without_replacement(events, replacement):
    return [
        event
        for event in events
        if not (
            replacement
            and event["id"] == replacement["id"]
            and event.get("source", "personal") == "personal"
        )
    ]


class AccountPlanning(AccountSnapshot):
    def propose(self, account_id, token, body, *, now=None, replacement=None):
        body = PlanningInput.model_validate(body)
        now = now or datetime.now(timezone.utc)
        deadline = time.monotonic() + 10
        with Session(self.engine) as db:
            require_account_session(db, account_id, token)
        snapshot = self.build(account_id)
        task = next((row for row in snapshot["tasks"] if row["id"] == body.task_id), None)
        if task is None or task["completed"]:
            raise LookupError("Task unavailable")
        zone = ZoneInfo(snapshot["settings"]["timezone"])
        today = now.astimezone(zone).date()
        if not today <= body.day <= today + timedelta(days=30):
            raise ValueError("Planning day outside range")
        slot, overdue = choose_slot(
            body,
            task["due"],
            without_replacement(snapshot["events"], replacement),
            now,
            zone,
            deadline,
        )
        if slot is None:
            return {"proposal": None, "reason": "no_slot"}
        event = EventInput(
            title=task["title"],
            notes="Task time block · LifeOS",
            start=slot[0].isoformat(),
            end=slot[1].isoformat(),
        ).model_dump()
        original = signature(SimpleNamespace(**task))
        id = str(uuid4())
        with Session(self.engine) as db:
            begin_academic_write(db)
            session = require_account_session(db, account_id, token)
            current = db.scalar(
                select(Task).where(Task.id == body.task_id, Task.account_id == account_id, actionable_tasks())
            )
            if current is None or signature(current) != original:
                raise ValueError("Task changed; retry")
            link = db.get(TaskTimeBlock, body.task_id)
            if link:
                existing = db.get(CalendarEvent, link.event_id)
                if existing is None or existing.account_id != account_id:
                    raise PermissionError("Time block owner mismatch")
                if replacement:
                    verify_replacement(existing, replacement, now)
                    event["notes"] = existing.notes
                elif datetime.fromisoformat(existing.end.replace("Z", "+00:00")) > now:
                    raise ValueError("Task already planned")
            elif replacement:
                raise ValueError("Work block no longer linked")
            db.execute(
                delete(AssistantProposal).where(
                    AssistantProposal.session_hash == session.token_hash,
                    AssistantProposal.expires < int(time.time()),
                    AssistantProposal.confirmed_id.is_(None),
                )
            )
            pending = db.scalar(
                select(func.count())
                .select_from(AssistantProposal)
                .where(
                    AssistantProposal.session_hash == session.token_hash,
                    AssistantProposal.confirmed_id.is_(None),
                )
            )
            if pending >= 20:
                raise ValueError("Too many pending proposals")
            payload = {
                "account_id": account_id,
                "task_id": body.task_id,
                "signature": original,
                "timezone": zone.key,
                "request": body.model_dump(mode="json"),
                "record": event,
                **({"replacement": replacement} if replacement else {}),
            }
            db.add(
                AssistantProposal(
                    id=id,
                    session_hash=session.token_hash,
                    kind="account_task_plan",
                    payload=json.dumps(payload),
                    expires=int(time.time()) + 900,
                )
            )
            db.commit()
        return {"proposal": {"id": id, "record": event, "overdue": overdue}}

    def confirm(self, account_id, token, proposal_id, *, now=None):
        now = now or datetime.now(timezone.utc)
        deadline = time.monotonic() + 10
        with Session(self.engine) as db:
            begin_academic_write(db)
            session = require_account_session(db, account_id, token)
            stored = db.get(AssistantProposal, proposal_id)
            if (
                stored is None
                or stored.session_hash != session.token_hash
                or stored.kind != "account_task_plan"
            ):
                raise LookupError("Proposal not found")
            payload = json.loads(stored.payload)
            if payload["account_id"] != account_id:
                raise PermissionError("Proposal owner mismatch")
            if stored.confirmed_id:
                existing = db.get(CalendarEvent, stored.confirmed_id)
                if existing is None or existing.account_id != account_id:
                    raise LookupError("Saved time block unavailable")
                return {"id": existing.id, "start": existing.start, "end": existing.end}
            if stored.expires <= int(time.time()):
                raise ValueError("Proposal expired")
            if "proactive_guard" in payload:
                from .proactive_planning import verify_proactive_guard

                verify_proactive_guard(db, account_id, payload["proactive_guard"], now)
            task = db.scalar(
                select(Task).where(Task.id == payload["task_id"], Task.account_id == account_id, actionable_tasks())
            )
            if task is None or signature(task) != payload["signature"]:
                raise ValueError("Task changed; make a new proposal")
            link = db.get(TaskTimeBlock, task.id)
            replacement = payload.get("replacement")
            linked = None
            if link:
                linked = db.get(CalendarEvent, link.event_id)
                if linked is None or linked.account_id != account_id:
                    raise PermissionError("Time block owner mismatch")
                if replacement:
                    verify_replacement(linked, replacement, now)
                elif datetime.fromisoformat(linked.end.replace("Z", "+00:00")) > now:
                    raise ValueError("Task already planned")
            elif replacement:
                raise ValueError("Work block no longer linked")
            snapshot = self.build(account_id, db=db)
            if snapshot["settings"]["timezone"] != payload["timezone"]:
                raise ValueError("Timezone changed")
            body = PlanningInput.model_validate(payload["request"])
            slot, _ = choose_slot(
                body,
                task.due,
                without_replacement(snapshot["events"], replacement),
                now,
                ZoneInfo(payload["timezone"]),
                deadline,
            )
            expected = payload["record"]
            if (
                slot is None
                or tuple(
                    datetime.fromisoformat(expected[key].replace("Z", "+00:00"))
                    for key in ("start", "end")
                )
                != slot
            ):
                raise ValueError("Calendar changed; make a new proposal")
            if replacement:
                row = linked
                for key, value in EventInput.model_validate(expected).model_dump().items():
                    setattr(row, key, value)
            else:
                row = CalendarEvent(
                    id=str(uuid4()),
                    account_id=account_id,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    **EventInput.model_validate(expected).model_dump(),
                )
            db.add(row)
            db.flush()
            link = db.get(TaskTimeBlock, task.id)
            if link is None:
                db.add(TaskTimeBlock(task_id=task.id, event_id=row.id))
            else:
                link.event_id = row.id
            stored.confirmed_id = row.id
            result = {"id": row.id, "start": row.start, "end": row.end}
            db.commit()
            return result
