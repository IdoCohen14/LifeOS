"""Owned unified-calendar input for planning and briefings; no global services."""

import json
from contextlib import nullcontext
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .academic_calendar import iter_calendar
from .academic_reads import ReadBudget
from .account_records import AccountRecords
from .briefings import summarize
from .models import AccountPreference, AccountProviderRecord, CalendarEvent, Task
from .schemas import EventOutput, SettingsPatch, TaskOutput
from .task_scope import actionable_tasks


class AccountSnapshot(AccountRecords):
    def build(self, account_id, *, db=None):
        budget = ReadBudget()
        supplied = db is not None
        with nullcontext(db) if supplied else Session(self.engine) as db:
            if not supplied:
                db.execute(text("BEGIN"))
            self.authorize(db, account_id)
            pref = db.get(AccountPreference, (account_id, "settings"))
            settings = SettingsPatch.model_validate(
                json.loads(pref.payload) if pref else {}
            ).model_dump()
            tasks = [
                TaskOutput.model_validate(row).model_dump()
                for row in budget.collect(
                    db.scalars(
                        select(Task).where(Task.account_id == account_id, actionable_tasks()).limit(10001)
                    ).yield_per(200)
                )
            ]
            events = [
                EventOutput.model_validate(row).model_dump()
                for row in budget.collect(
                    db.scalars(
                        select(CalendarEvent)
                        .where(CalendarEvent.account_id == account_id)
                        .limit(10001)
                    ).yield_per(200)
                )
            ]
            events.extend(budget.collect(iter_calendar(db, budget.check, account_id=account_id)))
            from .moodle_academic import visible_events

            moodle_records = []
            for row in db.scalars(
                select(AccountProviderRecord).where(
                    AccountProviderRecord.account_id == account_id,
                    AccountProviderRecord.provider.in_(["google", "moodle", "braude"]),
                )
            ).yield_per(200):
                budget.check()
                record = json.loads(row.payload)
                if row.provider == "moodle":
                    moodle_records.append(record)
                    continue
                if row.provider == "google":
                    if record.get("kind") != "visible":
                        continue
                    record = record["payload"]
                events.append(EventOutput.model_validate(record).model_dump())
                if len(events) > 10000:
                    raise ValueError("Account calendar resource limit")
            events.extend(EventOutput.model_validate(record).model_dump()
                          for record in visible_events(db, account_id, moodle_records))
            if len(events) > 10000:
                raise ValueError("Account calendar resource limit")
            budget.check()
            return {
                "tasks": tasks,
                "events": sorted(events, key=lambda event: event["start"]),
                "settings": settings,
            }

    def briefing(self, account_id, days=1, *, now=None):
        if days not in (1, 7):
            raise ValueError("Unsupported briefing range")
        snapshot = self.build(account_id)
        now = now or datetime.now(timezone.utc)
        return summarize(
            [(task["due"], task["completed"]) for task in snapshot["tasks"]],
            snapshot["events"],
            now,
            snapshot["settings"]["timezone"],
            days,
        )
