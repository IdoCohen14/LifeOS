"""Bounded Gmail history delta traversal with explicit full-snapshot fallback."""

import re

from .google_calendar import GoogleProblem


def history_id(value):
    if value is None:
        return None
    value = str(value)
    return value if re.fullmatch(r"[0-9]{1,30}", value) else None


def history_changes(get, cursor):
    if not cursor:
        return None
    changed = set()
    page = None
    for _ in range(10):
        result = get(
            "/history",
            {"startHistoryId": cursor, "maxResults": 500, **({"pageToken": page} if page else {})},
        )
        if result is None:
            return None
        if not isinstance(result, dict) or not isinstance(result.get("history", []), list):
            raise GoogleProblem("invalid_provider_response")
        for entry in result.get("history", []):
            if not isinstance(entry, dict):
                raise GoogleProblem("invalid_provider_response")
            source = entry.get("messages", [])
            if not isinstance(source, list):
                raise GoogleProblem("invalid_provider_response")
            messages = list(source)
            for kind in ("messagesAdded", "messagesDeleted", "labelsAdded", "labelsRemoved"):
                items = entry.get(kind, [])
                if not isinstance(items, list):
                    raise GoogleProblem("invalid_provider_response")
                for item in items:
                    if not isinstance(item, dict):
                        raise GoogleProblem("invalid_provider_response")
                    messages.append(item.get("message"))
            for message in messages:
                if not isinstance(message, dict):
                    raise GoogleProblem("invalid_provider_response")
                id = message.get("id")
                if not isinstance(id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", id):
                    raise GoogleProblem("invalid_provider_response")
                changed.add(id)
            if len(changed) > 5000:
                return None
        page = result.get("nextPageToken")
        if not page:
            checkpoint = history_id(result.get("historyId"))
            return (changed, checkpoint) if checkpoint else None
    return None
