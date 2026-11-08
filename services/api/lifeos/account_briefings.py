"""Opt-in cached numeric briefings scoped to one enabled account."""

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .academic import begin_academic_write
from .account_snapshot import AccountSnapshot
from .briefings import ScheduleInput, occurrence, summarize, week_start
from .models import AccountBriefing, AccountPreference, AccountProvider
from .recommendations import stable_id
from .schemas import SettingsPatch


class AccountBriefings(AccountSnapshot):
    def config(self, db, account_id):
        row = db.get(AccountPreference, (account_id, "briefings"))
        settings = db.get(AccountPreference, (account_id, "settings"))
        return (
            ScheduleInput.model_validate(json.loads(row.payload) if row else {}),
            SettingsPatch.model_validate(json.loads(settings.payload) if settings else {}).timezone,
        )

    def generate_due(self, account_id, *, now=None):
        now = now or datetime.now(timezone.utc)
        if now.utcoffset() is None:
            raise ValueError("UTC offset required")
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, account_id)
            config, zone_name = self.config(db, account_id)
            zone = ZoneInfo(zone_name)
            day = now.astimezone(zone).date()
            week = week_start(day)
            slots = []
            for enabled, kind, scheduled, clock, period, length in (
                (config.daily_enabled, "daily_briefing", day, config.daily_time, day, 1),
                (
                    config.weekly_enabled,
                    "weekly_briefing",
                    week + timedelta(days=(config.weekly_day + 1) % 7),
                    config.weekly_time,
                    week,
                    7,
                ),
            ):
                if enabled and occurrence(scheduled, clock, zone) <= now:
                    id = stable_id(kind, [period.isoformat(), zone_name])
                    if db.get(AccountBriefing, (account_id, id)) is None:
                        slots.append((id, kind, period, length))
            if not slots:
                return 0
            snapshot = self.build(account_id, db=db)
            stale = [
                {"google": "Google Calendar", "moodle": "Moodle", "braude": "Braude"}[row.provider]
                for row in db.scalars(
                    select(AccountProvider).where(
                        AccountProvider.account_id == account_id,
                        AccountProvider.provider.in_(["google", "moodle", "braude"]),
                    )
                )
                if row.authorized
                and (
                    row.error
                    or row.last_success is None
                    or now.timestamp() - row.last_success > 1800
                )
            ]
            for id, kind, period, length in slots:
                payload = summarize(
                    [(row["due"], row["completed"]) for row in snapshot["tasks"]],
                    snapshot["events"],
                    now,
                    zone_name,
                    length,
                )
                payload.update(
                    stale_sources=stale, generated_at=now.isoformat(), timezone=zone_name
                )
                db.add(
                    AccountBriefing(
                        account_id=account_id,
                        id=id,
                        kind=kind,
                        period_start=period.isoformat(),
                        timezone=zone_name,
                        generated_at=now.isoformat(),
                        payload=json.dumps(payload),
                    )
                )
            db.execute(
                delete(AccountBriefing).where(
                    AccountBriefing.account_id == account_id,
                    AccountBriefing.generated_at < (now - timedelta(days=90)).isoformat(),
                )
            )
            db.commit()
            return len(slots)

    def candidates(self, account_id, *, now=None):
        now = now or datetime.now(timezone.utc)
        with Session(self.engine) as db:
            self.authorize(db, account_id)
            config, zone_name = self.config(db, account_id)
            day = now.astimezone(ZoneInfo(zone_name)).date()
            periods = {}
            if config.daily_enabled:
                periods["daily_briefing"] = day.isoformat()
            if config.weekly_enabled:
                periods["weekly_briefing"] = week_start(day).isoformat()
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
                for row in db.scalars(
                    select(AccountBriefing).where(
                        AccountBriefing.account_id == account_id,
                        AccountBriefing.timezone == zone_name,
                        AccountBriefing.period_start >= week_start(day).isoformat(),
                    )
                )
                if periods.get(row.kind) == row.period_start
            ]
