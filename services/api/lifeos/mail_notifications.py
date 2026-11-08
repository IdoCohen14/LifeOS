"""Local cached mail candidates; no provider calls or mailbox mutations."""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .gmail_models import GmailConnection, GmailMessage, GmailReviewed
from .mail_filter import relevant
from .recommendations import stable_id


def mail_candidates(engine):
    with Session(engine) as db:
        connection = db.get(GmailConnection, 1)
        if not connection or connection.state not in ("connected", "error"):
            return []
        rows = list(db.scalars(select(GmailMessage).limit(50)))
        ids = [row.id for row in rows]
        reviewed = set(db.scalars(select(GmailReviewed.id).where(GmailReviewed.id.in_(ids))))
        items = []
        for row in rows:
            message = json.loads(row.payload)
            if row.id in reviewed or not message.get("unread") or not relevant(message):
                continue
            items.append(
                {
                    "id": stable_id("new_mail", [row.id]),
                    "kind": "new_mail",
                    "title": message.get("subject", ""),
                    "target": "dashboard",
                    "source_ids": [row.id],
                    "priority": 3,
                    "order": str(message.get("received_at", 0)),
                    "source": "Gmail",
                }
            )
        return items
