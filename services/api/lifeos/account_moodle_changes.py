"""Minimal owned Moodle observations committed with the provider snapshot."""

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .account_records import AccountRecords
from .models import AccountMoodleChange, AccountProviderRecord
from .moodle_changes import projection
from .recommendations import stable_id


def record_changes(db, account_id, events, observed_at, *, baseline):
    if not baseline:
        previous = {
            row.external_id: projection(json.loads(row.payload))
            for row in db.scalars(
                select(AccountProviderRecord).where(
                    AccountProviderRecord.account_id == account_id,
                    AccountProviderRecord.provider == "moodle",
                )
            )
        }
        current = {row["id"]: projection(row) for row in events}
        for id in sorted(previous.keys() | current.keys()):
            old, new = previous.get(id), current.get(id)
            if old != new:
                db.add(
                    AccountMoodleChange(
                        account_id=account_id,
                        id=str(uuid4()),
                        event_id=id,
                        kind="added" if old is None else "removed" if new is None else "changed",
                        previous=json.dumps(old) if old else None,
                        current=json.dumps(new) if new else None,
                        observed_at=observed_at,
                    )
                )
    db.flush()
    keep = (
        select(AccountMoodleChange.id)
        .where(
            AccountMoodleChange.account_id == account_id,
            AccountMoodleChange.observed_at >= observed_at - 30 * 86400,
        )
        .order_by(AccountMoodleChange.observed_at.desc(), AccountMoodleChange.id)
        .limit(200)
    )
    db.execute(
        delete(AccountMoodleChange)
        .where(
            AccountMoodleChange.account_id == account_id,
            AccountMoodleChange.id.not_in(keep),
        )
        .execution_options(synchronize_session=False)
    )


class AccountMoodleChanges(AccountRecords):
    def list(self, account_id):
        with Session(self.engine) as db:
            self.authorize(db, account_id)
            return [
                {
                    "id": row.id,
                    "event_id": row.event_id,
                    "kind": row.kind,
                    "previous": json.loads(row.previous) if row.previous else None,
                    "current": json.loads(row.current) if row.current else None,
                    "observed_at": row.observed_at,
                }
                for row in db.scalars(
                    select(AccountMoodleChange)
                    .where(
                        AccountMoodleChange.account_id == account_id,
                    )
                    .order_by(AccountMoodleChange.observed_at.desc(), AccountMoodleChange.id)
                    .limit(20)
                )
            ]

    def candidates(self, account_id):
        now = datetime.now(timezone.utc)
        items = []
        for row in self.list(account_id):
            event = row["current"] or row["previous"]
            if row["observed_at"] < now.timestamp() - 86400 or not event:
                continue
            old = row["previous"]
            items.append(
                {
                    "id": stable_id("moodle_update", [row["id"]]),
                    "kind": "moodle_update",
                    "title": event["title"],
                    "start": event["start"],
                    "target": "calendar",
                    "event_source": "moodle",
                    "source_ids": [row["event_id"]],
                    "change_kind": row["kind"],
                    "observed_at": row["observed_at"],
                    "previous_start": old["start"]
                    if old and row["current"] and old["start"] != event["start"]
                    else None,
                    "priority": 3,
                    "order": datetime.fromtimestamp(row["observed_at"], timezone.utc).isoformat(),
                }
            )
        return items
