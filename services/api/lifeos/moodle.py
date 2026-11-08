"""Braude's authorized private iCalendar feed. No login scraping or Moodle writes."""

import hashlib
import json
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

from icalendar import Calendar
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from .data_lock import runtime_lock
from .google_calendar import GoogleCalendarService, GoogleProblem
from .moodle_changes import MoodleChange, list_changes, record_changes
from .moodle_models import MoodleConnection, MoodleEvent
from .moodle_versions import choose_version, modified_at
from .schemas import EventInput

HOSTS = {"moodle27.braude.ac.il", "moodle24.braude.ac.il"}
MAX_BYTES = 2 * 1024 * 1024


def validate_url(url):
    try:
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        if (
            len(url) > 8192
            or parsed.scheme != "https"
            or parsed.hostname not in HOSTS
            or parsed.port not in (None, 443)
            or parsed.username
            or parsed.password
            or parsed.fragment
            or parsed.path != "/calendar/export_execute.php"
            or not query.get("authtoken")
            or any(ord(c) < 33 for c in url)
        ):
            raise ValueError()
    except Exception:
        raise GoogleProblem("invalid_moodle_url", 422) from None
    return url


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def parse_feed(content, host):
    if len(content) > MAX_BYTES:
        raise GoogleProblem("feed_too_large")
    if not content.lstrip().startswith(b"BEGIN:VCALENDAR"):
        raise GoogleProblem("invalid_calendar_feed")
    try:
        calendar = Calendar.from_ical(content)
        if calendar.errors:
            raise ValueError()
        result = {}
        for index, event in enumerate(calendar.walk("VEVENT")):
            if index >= 5000:
                raise GoogleProblem("event_limit_exceeded")
            if event.errors:
                raise ValueError()
            if (
                event.get("RRULE")
                or event.get("RECURRENCE-ID")
                or event.get("RDATE")
                or event.get("EXDATE")
            ):
                raise GoogleProblem("recurrence_not_supported")
            if str(event.get("STATUS", "")).upper() == "CANCELLED":
                continue
            uid = str(event["UID"])
            if not uid or len(uid) > 4096:
                raise ValueError()
            begin = event.decoded("DTSTART")
            all_day = isinstance(begin, date) and not isinstance(begin, datetime)
            end = (
                event.decoded("DTEND")
                if "DTEND" in event
                else begin
                + event.decoded("DURATION", timedelta(days=1) if all_day else timedelta(minutes=1))
            )
            if all_day:
                if not isinstance(end, date) or isinstance(end, datetime):
                    raise ValueError()
                if end == begin:
                    end = begin + timedelta(days=1)
                start_value, end_value = begin.isoformat(), end.isoformat()
            else:
                for value in (begin, end):
                    if not isinstance(value, datetime) or value.tzinfo is None:
                        raise GoogleProblem("floating_time_not_supported")
                    if value.replace(fold=0).utcoffset() != value.replace(fold=1).utcoffset():
                        raise GoogleProblem("ambiguous_calendar_time")
                    if value.astimezone(timezone.utc).astimezone(value.tzinfo).replace(
                        tzinfo=None
                    ) != value.replace(tzinfo=None):
                        raise GoogleProblem("invalid_calendar_time")
                if end == begin:
                    end = begin + timedelta(minutes=1)
                start_value = begin.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                end_value = end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            plain = PlainText()
            plain.feed(str(event.get("DESCRIPTION", "")))
            notes = " ".join(plain.parts)[:10000]
            # Keep only non-secret Moodle source URLs; never expose subscription tokens.
            link = f"https://{host}/calendar/view.php"
            proposed = str(event.get("URL", ""))
            source = urlsplit(proposed)
            if (
                source.scheme == "https"
                and source.netloc == host
                and source.path != "/calendar/export_execute.php"
                and not source.fragment
                and set(parse_qs(source.query)) <= {"id", "view", "time", "course"}
            ):
                link = proposed
            record = EventInput(
                title=str(event.get("SUMMARY") or "Moodle")[:240],
                notes=notes,
                start=start_value,
                end=end_value,
                all_day=all_day,
            ).model_dump()
            eid = "moodle-" + hashlib.sha256((host + "\0" + uid).encode()).hexdigest()
            candidate = {
                **record,
                "id": eid,
                "source": "moodle",
                "source_url": link,
                "created_at": "1970-01-01T00:00:00Z",
                "course_categories": [str(value)[:500] for value in
                                      getattr(event.get("CATEGORIES"), "cats", [])][:20],
            }
            modified = modified_at(event)
            if modified is not None:
                candidate["source_modified_at"] = modified
            result[eid] = choose_version(result[eid], candidate, same_feed=True) if eid in result else candidate
        return list(result.values())
    except GoogleProblem:
        raise
    except Exception:
        raise GoogleProblem("invalid_calendar_feed") from None


class MoodleService(GoogleCalendarService):
    Connection = MoodleConnection
    Cache = MoodleEvent

    def clear_cache(self, db):
        super().clear_cache(db)
        db.execute(delete(MoodleChange))

    def changes(self):
        with Session(self.engine) as db:
            return list_changes(db)

    def locked_connection(self, db):
        # Reserve SQLite's write lock before reading lease/configuration state.
        db.execute(
            insert(MoodleConnection)
            .values(id=1, state="disconnected", next_sync=0, failures=0, lease_until=0)
            .on_conflict_do_nothing(index_elements=["id"])
        )
        return self.connection(db)

    def configure_feed(self, url):
        validate_url(url)
        with Session(self.engine) as db:
            row = self.locked_connection(db)
            self.unlocked(row)
            row.credentials = self.vault.encrypt({"url": url})
            row.state, row.error, row.last_success = "configured", None, None
            row.next_sync, row.failures = int(time.time()), 0
            row.lease_owner, row.lease_until = None, 0
            self.clear_cache(db)
            db.commit()
        return self.status()

    def disconnect(self):
        with Session(self.engine) as db:
            row = self.locked_connection(db)
            self.unlocked(row)
            row.credentials, row.state, row.error = None, "disconnected", None
            row.last_success, row.next_sync, row.lease_owner, row.lease_until = None, 0, None, 0
            self.clear_cache(db)
            db.commit()

    def status(self):
        with Session(self.engine) as db:
            row = db.get(MoodleConnection, 1)
            return {
                "configured": bool(row and row.credentials),
                "connected": bool(row and row.last_success is not None),
                "state": row.state if row else "disconnected",
                "error": row.error if row else None,
                "last_success": row.last_success if row else None,
                "event_count": db.scalar(select(func.count()).select_from(MoodleEvent)),
                "next_sync": row.next_sync if row else None,
                "syncing": bool(row and row.lease_owner and row.lease_until > time.time()),
                "stale": bool(row and row.last_success and time.time() - row.last_success > 1800),
            }

    def events(self):
        with Session(self.engine) as db:
            return [json.loads(row.payload) for row in db.scalars(select(MoodleEvent))]

    def sync(self):
        with runtime_lock(self.vault.directory):
            return self._sync()

    def _sync(self):
        now, owner = int(time.time()), secrets.token_hex(16)
        with Session(self.engine) as db:
            acquired = db.execute(
                update(MoodleConnection)
                .where(
                    MoodleConnection.id == 1,
                    MoodleConnection.lease_until <= now,
                    MoodleConnection.credentials.is_not(None),
                )
                .values(lease_owner=owner, lease_until=now + 90)
                .returning(MoodleConnection.credentials)
            ).first()
            if acquired is None:
                row = db.get(MoodleConnection, 1)
                if row is None or row.credentials is None:
                    raise GoogleProblem("not_configured", 409)
                raise GoogleProblem("sync_in_progress", 409)
            credentials = acquired[0]
            db.commit()
        try:
            try:
                values = self.vault.decrypt(credentials)
            except Exception:
                raise GoogleProblem("credentials_unavailable") from None
            url = validate_url(values["url"])
            chunks, size, started = [], 0, time.monotonic()
            with self.http.stream(
                "GET",
                url,
                follow_redirects=False,
                timeout=15,
                headers={"Accept": "text/calendar", "Accept-Encoding": "identity"},
            ) as response:
                if response.status_code in (401, 403):
                    raise GoogleProblem("feed_access_denied")
                if response.status_code != 200:
                    raise GoogleProblem("feed_unavailable")
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise GoogleProblem("compressed_feed_not_supported")
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise GoogleProblem("feed_too_large")
                    if time.monotonic() - started > 30:
                        raise GoogleProblem("feed_timeout")
                    chunks.append(chunk)
            events = parse_feed(b"".join(chunks), urlsplit(url).hostname)
            with Session(self.engine) as db:
                fence = db.execute(
                    update(MoodleConnection)
                    .where(MoodleConnection.id == 1, MoodleConnection.lease_owner == owner)
                    .values(lease_owner=None, lease_until=0)
                )
                if fence.rowcount != 1:
                    raise GoogleProblem("sync_lease_lost", 409)
                row = db.get(MoodleConnection, 1)
                record_changes(db, events, int(time.time()), baseline=row.last_success is None)
                db.execute(delete(MoodleEvent))
                db.add_all(MoodleEvent(id=e["id"], payload=json.dumps(e)) for e in events)
                row = db.get(MoodleConnection, 1)
                row.state, row.error, row.failures = "connected", None, 0
                row.last_success, row.next_sync = int(time.time()), int(time.time()) + 600
                db.commit()
        except Exception as error:
            problem = (
                error if isinstance(error, GoogleProblem) else GoogleProblem("feed_unavailable")
            )
            with Session(self.engine) as db:
                row = db.get(MoodleConnection, 1)
                if row and row.lease_owner == owner:
                    row.state, row.error = "error", problem.code
                    row.failures += 1
                    row.next_sync = int(time.time()) + min(3600, 60 * 2 ** min(row.failures, 6))
                    row.lease_owner, row.lease_until = None, 0
                    db.commit()
            raise problem from None
        return self.status()
