"""Validated account preferences, isolated from legacy singleton settings."""

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from .academic import begin_academic_write
from .account_records import AccountRecords
from .braude_academic import BraudeAcademicState
from .briefings import ScheduleInput, occurrence
from .conversation_history import HistoryPreference
from .mail_calendar import MailCalendarPreference
from .models import AccountPreference
from .moodle_academic import MoodleAcademicState
from .notifications import Preferences
from .planning_preferences import DEFAULTS, PreferenceInput
from .request_models import RequestState
from .schemas import SettingsPatch
from .secretary_preferences import SecretaryPreferences

SPECS = {
    'secretary': (SecretaryPreferences, SecretaryPreferences().model_dump()),
    "assistant_requests": (RequestState, RequestState().model_dump()),
    "moodle_academic": (MoodleAcademicState, MoodleAcademicState().model_dump()),
    "braude_academic": (BraudeAcademicState, BraudeAcademicState().model_dump()),
    "mail_calendar": (MailCalendarPreference, MailCalendarPreference().model_dump()),
    "settings": (SettingsPatch, SettingsPatch().model_dump()),
    "planning": (PreferenceInput, DEFAULTS),
    "notifications": (Preferences, Preferences().model_dump()),
    "history": (HistoryPreference, {"enabled": False}),
    "briefings": (ScheduleInput, ScheduleInput().model_dump()),
}


class AccountPreferences(AccountRecords):
    def get(self, account_id, kind):
        _, defaults = SPECS[kind]
        with Session(self.engine) as db:
            self.authorize(db, account_id)
            row = db.get(AccountPreference, (account_id, kind))
            return {
                "revision": row.revision if row else 0,
                "values": json.loads(row.payload) if row else json.loads(json.dumps(defaults)),
            }

    def put(self, account_id, kind, values, revision, *, reset=False):
        schema, defaults = SPECS[kind]
        if type(revision) is not int or revision < 0:
            raise ValueError("Invalid revision")
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, account_id)
            row = db.get(AccountPreference, (account_id, kind))
            current = row.revision if row else 0
            if current != revision:
                raise ValueError("Preferences changed; reload")
            previous = json.loads(row.payload) if row else dict(defaults)
            merged = dict(defaults) if reset else {**previous, **values}
            if schema is PreferenceInput:
                merged["revision"] = revision
            validated = schema.model_validate(merged).model_dump(mode="json")
            validated.pop("revision", None)
            if kind in ("settings", "briefings"):
                setting = db.get(AccountPreference, (account_id, "settings"))
                schedule = db.get(AccountPreference, (account_id, "briefings"))
                zone_name = (
                    validated["timezone"]
                    if kind == "settings"
                    else SettingsPatch.model_validate(
                        json.loads(setting.payload) if setting else {}
                    ).timezone
                )
                config = ScheduleInput.model_validate(
                    validated
                    if kind == "briefings"
                    else json.loads(schedule.payload)
                    if schedule
                    else {}
                )
                zone = ZoneInfo(zone_name)
                today = datetime.now(timezone.utc).astimezone(zone).date()
                for offset in range(371):
                    day = today + timedelta(days=offset)
                    if config.daily_enabled:
                        occurrence(day, config.daily_time, zone)
                    if config.weekly_enabled and day.weekday() == config.weekly_day:
                        occurrence(day, config.weekly_time, zone)
            if row is None:
                row = AccountPreference(account_id=account_id, kind=kind)
                db.add(row)
            row.revision, row.payload = current + 1, json.dumps(validated, ensure_ascii=False)
            db.commit()
            return {"revision": current + 1, "values": validated}
