"""Shared metadata projection for legacy and account-scoped Gmail."""

import html
import re


def parse_message(message, mid, source_prefix):
    headers = {
        h.get("name", "").lower(): str(h.get("value", ""))
        for h in message.get("payload", {}).get("headers", [])
    }
    labels = message.get("labelIds", [])
    thread = message.get("threadId")
    if not isinstance(thread, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", thread):
        thread = mid
    return {
        "id": mid,
        "thread_id": thread,
        "subject": headers.get("subject", "")[:1000],
        "sender": headers.get("from", "")[:1000],
        "snippet": html.unescape(str(message.get("snippet", "")))[:2000],
        "received_at": int(message.get("internalDate", 0)),
        "unread": "UNREAD" in labels,
        "important": "IMPORTANT" in labels,
        "labels": labels,
        "bulk": bool(headers.get("list-unsubscribe"))
        or headers.get("precedence", "").lower() in ("bulk", "list")
        or headers.get("auto-submitted", "no").lower() != "no",
        "source_url": source_prefix + mid,
    }
