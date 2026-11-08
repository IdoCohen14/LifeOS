"""Account-scoped relevant cached mail and local-only review state."""

import json
from collections import Counter

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .academic import begin_academic_write
from .account_records import AccountRecords
from .mail_filter import relevant
from .models import AccountMailReview, AccountProvider, AccountProviderRecord


class AccountMail(AccountRecords):
    def snapshot(self, db, account_id):
        connection = db.get(AccountProvider, (account_id, "gmail"))
        revision = connection.revision if connection else 0
        raw = [
            json.loads(row.payload)
            for row in db.scalars(
                select(AccountProviderRecord).where(
                    AccountProviderRecord.account_id == account_id,
                    AccountProviderRecord.provider == "gmail",
                )
            )
        ]
        messages = sorted(
            (row for row in raw if relevant(row)), key=lambda row: row["received_at"], reverse=True
        )
        counts = Counter(row.get("thread_id") or row["id"] for row in messages)
        messages = [
            {**row, "cached_thread_count": counts[row.get("thread_id") or row["id"]]}
            for row in messages
        ]
        reviewed = set(
            db.scalars(
                select(AccountMailReview.message_id).where(
                    AccountMailReview.account_id == account_id,
                    AccountMailReview.provider_revision == revision,
                )
            )
        )
        return {
            "revision": revision,
            "messages": messages,
            "queue": [row for row in messages if row.get("unread") and row["id"] not in reviewed],
        }

    def get(self, account_id):
        with Session(self.engine) as db:
            db.execute(text("BEGIN"))
            self.authorize(db, account_id)
            return self.snapshot(db, account_id)

    def review(self, account_id, revision, *, message_id=None, all=False, undo=False):
        if (
            type(revision) is not int
            or type(all) is not bool
            or type(undo) is not bool
            or all
            and (undo or message_id is not None)
            or not all
            and not isinstance(message_id, str)
        ):
            raise ValueError("Invalid mail review")
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, account_id)
            snapshot = self.snapshot(db, account_id)
            if snapshot["revision"] != revision:
                raise ValueError("Mail connection changed; reload")
            allowed = {row["id"] for row in snapshot["messages"] if row.get("unread")}
            if message_id is not None and message_id not in allowed:
                raise LookupError("Message not found")
            ids = [row["id"] for row in snapshot["queue"]] if all else [message_id]
            for id in ids:
                key = (account_id, revision, id)
                row = db.get(AccountMailReview, key)
                if undo:
                    if row is not None:
                        db.delete(row)
                elif row is None:
                    db.add(
                        AccountMailReview(
                            account_id=account_id, provider_revision=revision, message_id=id
                        )
                    )
            db.flush()
            result = self.snapshot(db, account_id)
            db.commit()
            return result
