"""Resolve repeated source identities only when the calendar proves their order."""

from datetime import datetime, timedelta

from .google_calendar import GoogleProblem


def modified_at(event):
    value = event.decoded("LAST-MODIFIED", None)
    # RFC5545 LAST-MODIFIED is UTC, not a floating date or local wall clock.
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        return None
    return value.isoformat().replace("+00:00", "Z")


def choose_version(previous, current, *, same_feed=False):
    old, new = previous.get("source_modified_at"), current.get("source_modified_at")
    if old and new:
        old_time, new_time = datetime.fromisoformat(old), datetime.fromisoformat(new)
        if old_time != new_time:
            return previous if old_time > new_time else current
    if not same_feed:
        return current
    old_values = {k: v for k, v in previous.items() if k != "source_modified_at"}
    new_values = {k: v for k, v in current.items() if k != "source_modified_at"}
    if old_values != new_values:
        raise GoogleProblem("conflicting_calendar_event")
    return previous if old and not new else current
