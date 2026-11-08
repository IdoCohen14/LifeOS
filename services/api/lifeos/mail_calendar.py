"""Conservative automatic mail deadlines. Literal data extraction, never instructions."""

import json
import re
from datetime import date, datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import select

from .mail_filter import relevant
from .models import AccountPreference, AccountProviderRecord, CalendarEvent


class MailCalendarPreference(BaseModel):
    enabled: bool = False
    processed: list[str] = Field(default_factory=list, max_length=10000)


CRITICAL = re.compile(r"מבחן|בחינה|ראיון|פגישה|מועד אחרון|מועד הגשה|דדליין|\b(?:exam|interview|meeting|deadline)\b", re.I)
DATE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2}|\d{1,2}[/.]\d{1,2}[/.]\d{4})(?!\d)")
TIME = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")


def candidate(message, zone, today):
    subject = str(message.get("subject", ""))
    if not isinstance(message.get("calendar_text"), str):
        return None
    text = subject + "\n" + message["calendar_text"]
    if (not relevant(message) or not CRITICAL.search(subject) or len(text) > 20000
            or re.search(r"\b(?:UTC|GMT|EST|EDT|PST|PDT|CET|CEST)\b|[+-]\d{2}:\d{2}", text, re.I)
            or re.search(r"בוטל|בוטלה|נדחה|מבוטל|cancelled|canceled|postponed|rescheduled|תאריך חדש", text, re.I)
            or re.search(r"On .+wrote:|כתב/ה:|Forwarded message|Original Message", text, re.I)):
        return None
    # Require a field explicitly identifying the event date, not receipt dates,
    # historical dates or an unlabelled example in a message.
    dates = DATE.findall(text)
    if len(set(dates)) != 1 or not re.search(r"(?:תאריך|בתאריך|מועד|date|deadline)\s*[:\-]?\s*" + re.escape(dates[0]), text, re.I):
        return None
    try:
        value = dates[0]
        if "-" in value:
            day = date.fromisoformat(value)
        else:
            d, m, y = map(int, re.split(r"[/.]", value))
            if d <= 12 and m <= 12 and not re.search(r"תאריך|מועד", text):
                return None  # Do not guess DD/MM versus MM/DD in an English email.
            day = date(y, m, d)
        if not today <= day <= today + timedelta(days=365):
            return None
        times = TIME.findall(text)
        deadline = bool(re.search(r"מועד אחרון|מועד הגשה|דדליין|\bdeadline\b", subject, re.I))
        if not times and deadline:
            return {"start": day.isoformat(), "end": (day + timedelta(days=1)).isoformat(), "all_day": True}
        # Timed events require an explicit start/end range: no invented duration.
        if len(times) != 2 or not re.search(r"(?:בשעות|שעות|time)\s*:?\s*\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}", text, re.I):
            return None
        values = []
        for hour, minute in times:
            naive = datetime.combine(day, datetime.min.time()).replace(hour=int(hour), minute=int(minute))
            aware = naive.replace(tzinfo=ZoneInfo(zone))
            if (aware.replace(fold=0).utcoffset() != aware.replace(fold=1).utcoffset()
                    or aware.astimezone(timezone.utc).astimezone(ZoneInfo(zone)).replace(tzinfo=None) != naive):
                return None
            values.append(aware.astimezone(timezone.utc))
        if values[1] <= values[0]:
            return None
        return {"start": values[0].isoformat(), "end": values[1].isoformat(), "all_day": False}
    except (ValueError, TypeError):
        return None


def capture(db, account_id, messages):
    """Called inside the existing owned Gmail snapshot transaction."""
    row = db.get(AccountPreference, (account_id, "mail_calendar"))
    config = MailCalendarPreference.model_validate(json.loads(row.payload) if row else {})
    if not config.enabled:
        return 0
    setting = db.get(AccountPreference, (account_id, "settings"))
    zone = json.loads(setting.payload).get("timezone", "Asia/Jerusalem") if setting else "Asia/Jerusalem"
    today = datetime.now(ZoneInfo(zone)).date()
    seen, created = set(config.processed), 0
    slots = None

    def slot(title, values):
        def stamp(value):
            if len(value) == 10:
                return value
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
        return (re.sub(r"\s+", " ", title).strip().casefold(), stamp(values["start"]), stamp(values["end"]))

    for message in messages:
        data = candidate(message, zone, today)
        if data is None:
            continue
        if slots is None:
            slots = {slot(event.title, {"start": event.start, "end": event.end})
                     for event in db.scalars(select(CalendarEvent).where(CalendarEvent.account_id == account_id))}
            for record in db.scalars(select(AccountProviderRecord).where(
                    AccountProviderRecord.account_id == account_id, AccountProviderRecord.provider == "google")):
                cached = json.loads(record.payload)
                if cached.get("kind") == "visible":
                    value = cached["payload"]
                    slots.add(slot(value["title"], value))
        # A thread/date/range identity prevents duplicates and respects later
        # manual edits/deletion. A changed date is a different candidate; an
        # explicit reschedule message is intentionally excluded above.
        identity = str(uuid5(NAMESPACE_URL, account_id + "/" + str(message.get("thread_id") or message["id"]) + "/" + json.dumps(data, sort_keys=True)))
        if identity in seen or len(seen) >= 10000:
            continue
        seen.add(identity)
        signature = slot(str(message["subject"]), data)
        if signature in slots or db.get(CalendarEvent, identity) is not None:
            continue
        slots.add(signature)
        db.add(CalendarEvent(id=identity, account_id=account_id,
            title=str(message["subject"])[:240],
            notes="נוסף אוטומטית ממייל עם מועד מפורש.\n" + str(message.get("sender", ""))[:1000] + "\n" + str(message.get("source_url", ""))[:2048],
            created_at=datetime.now(timezone.utc).isoformat(), **data))
        created += 1
    config.processed = sorted(seen)
    row.payload = config.model_dump_json()
    row.revision += 1
    return created
