"""Bounded, atomic read-only Inbox snapshots; OAuth credentials isolated from Calendar."""

import json
import re
import secrets
import time
from collections import Counter
from urllib.parse import quote

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .data_lock import runtime_lock
from .gmail_history import history_changes, history_id
from .gmail_metadata import parse_message
from .gmail_models import GmailConnection, GmailMessage, GmailOAuthState, GmailReviewed
from .google_calendar import GoogleCalendarService, GoogleProblem
from .google_models import GoogleConnection
from .mail_filter import relevant

API = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailService(GoogleCalendarService):
    Connection = GmailConnection
    OAuthState = GmailOAuthState
    Cache = GmailMessage
    scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    state_prefix = "gmail."

    def clear_cache(self, db):
        super().clear_cache(db)
        db.execute(delete(GmailReviewed))
        row = db.get(GmailConnection, 1)
        if row is not None:
            row.history_id = None

    def queue(self):
        with Session(self.engine) as db:
            reviewed = set(db.scalars(select(GmailReviewed.id)))
        return [m for m in self.messages() if m.get("unread") and m["id"] not in reviewed]

    def review(self, id=None, all=False, undo=False):
        with Session(self.engine) as db:
            if undo:
                db.execute(delete(GmailReviewed).where(GmailReviewed.id == id))
                db.commit()
                return sorted(self.queue(), key=lambda message: message["id"] != id)
            reviewed = set(db.scalars(select(GmailReviewed.id)))
            for row in db.scalars(select(GmailMessage)):
                message = json.loads(row.payload)
                if (
                    (all or row.id == id)
                    and message.get("unread")
                    and relevant(message)
                    and row.id not in reviewed
                ):
                    db.add(GmailReviewed(id=row.id))
            db.commit()
        return self.queue()

    def connection(self, db):
        row = super().connection(db)
        if not row.credentials:
            calendar = db.get(GoogleConnection, 1)
            if calendar and calendar.credentials:
                config = self.secrets(calendar)
                row.credentials = self.vault.encrypt(
                    {k: config[k] for k in ("client_id", "client_secret")}
                )
                row.state = "configured"
        return row

    def status(self):
        with Session(self.engine) as db:
            row = self.connection(db)
            result = {
                "configured": bool(row.credentials),
                "connected": row.state in ("connected", "error"),
                "state": row.state,
                "error": row.error,
                "syncing": bool(row.lease_owner and row.lease_until > int(time.time())),
                "last_success": row.last_success,
                "next_sync": row.next_sync,
                "stale": bool(row.last_success and time.time() - row.last_success > 1800),
                "limit": 50,
            }
            db.commit()
            return result

    def messages(self):
        with Session(self.engine) as db:
            messages = [json.loads(row.payload) for row in db.scalars(select(GmailMessage))]
            items = sorted(
                (m for m in messages if relevant(m)), key=lambda m: m["received_at"], reverse=True
            )
            counts = Counter(m.get("thread_id") or m["id"] for m in items)
            return [
                {**m, "cached_thread_count": counts[m.get("thread_id") or m["id"]]} for m in items
            ]

    def sync(self):
        with runtime_lock(self.vault.directory):
            return self._sync()

    def _sync(self):
        now, owner = int(time.time()), secrets.token_hex(16)
        with Session(self.engine) as db:
            row = self.connection(db)
            values = self.secrets(row)
            if not values.get("refresh_token"):
                raise GoogleProblem("not_connected", 409)
            acquired = db.execute(
                update(GmailConnection)
                .where(
                    GmailConnection.id == 1,
                    GmailConnection.lease_until <= now,
                )
                .values(lease_owner=owner, lease_until=now + 300)
            )
            if acquired.rowcount != 1:
                raise GoogleProblem("sync_in_progress", 409)
            db.refresh(row)
            values = self.secrets(row)
            if not values.get("refresh_token"):
                raise GoogleProblem("not_connected", 409)
            cursor = row.history_id
            cached = {
                message.id: json.loads(message.payload)
                for message in db.scalars(select(GmailMessage).limit(50))
            }
            db.commit()

        def heartbeat():
            with Session(self.engine) as db:
                result = db.execute(
                    update(GmailConnection)
                    .where(
                        GmailConnection.id == 1,
                        GmailConnection.lease_owner == owner,
                    )
                    .values(lease_until=int(time.time()) + 300)
                )
                if result.rowcount != 1:
                    raise GoogleProblem("sync_lease_lost", 409)
                db.commit()

        def get(path, params=None):
            nonlocal values
            heartbeat()
            response = self._request(
                "GET",
                API + path,
                params=params,
                headers={"Authorization": "Bearer " + values["access_token"]},
            )
            if response.status_code == 401:
                values = self.token_request(
                    values,
                    {"refresh_token": values["refresh_token"], "grant_type": "refresh_token"},
                )
                response = self._request(
                    "GET",
                    API + path,
                    params=params,
                    headers={"Authorization": "Bearer " + values["access_token"]},
                )
            if response.status_code == 429:
                raise GoogleProblem("rate_limited")
            if response.status_code == 403:
                try:
                    reasons = {
                        item.get("reason")
                        for item in response.json().get("error", {}).get("errors", [])
                    }
                except (ValueError, TypeError, AttributeError):
                    reasons = set()
                if reasons & {
                    "rateLimitExceeded",
                    "userRateLimitExceeded",
                    "dailyLimitExceeded",
                    "quotaExceeded",
                }:
                    raise GoogleProblem("rate_limited")
                if reasons & {"accessNotConfigured", "serviceDisabled"}:
                    raise GoogleProblem("api_not_enabled")
                raise GoogleProblem("reauthorization_required", 409)
            if response.status_code == 401:
                raise GoogleProblem("reauthorization_required", 409)
            if response.status_code == 404:
                return None
            if not response.is_success:
                raise GoogleProblem("provider_unavailable")
            return response.json()

        try:
            if values.get("expires_at", 0) <= now + 60:
                values = self.token_request(
                    values,
                    {"refresh_token": values["refresh_token"], "grant_type": "refresh_token"},
                )
            listing = get("/messages", {"labelIds": "INBOX", "maxResults": 50})
            if not isinstance(listing, dict) or not isinstance(listing.get("messages", []), list):
                raise GoogleProblem("invalid_provider_response")
            profile = get("/profile")
            email = profile.get("emailAddress", "") if isinstance(profile, dict) else ""
            if not email or not isinstance(email, str):
                raise GoogleProblem("invalid_provider_response")
            baseline = history_id(profile.get("historyId"))
            delta = history_changes(get, cursor)
            checkpoint = delta[1] if delta else baseline
            source_prefix = (
                "https://mail.google.com/mail/?authuser=" + quote(email, safe="") + "#all/"
            )
            staged = []
            for entry in listing.get("messages", [])[:50]:
                mid = entry.get("id", "")
                if not isinstance(mid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", mid):
                    raise GoogleProblem("invalid_provider_response")
                if (
                    delta is not None
                    and mid not in delta[0]
                    and mid in cached
                    and "thread_id" in cached[mid]
                ):
                    staged.append({**cached[mid], "source_url": source_prefix + mid})
                    continue
                message = get(
                    "/messages/" + mid,
                    {
                        "format": "metadata",
                        "metadataHeaders": [
                            "Subject",
                            "From",
                            "List-Unsubscribe",
                            "Auto-Submitted",
                            "Precedence",
                        ],
                    },
                )
                if message is None or "INBOX" not in message.get("labelIds", []):
                    continue  # Deleted/archived during synchronization.
                staged.append(parse_message(message, mid, source_prefix))
            with Session(self.engine) as db:
                fence = db.execute(
                    update(GmailConnection)
                    .where(GmailConnection.id == 1, GmailConnection.lease_owner == owner)
                    .values(lease_until=0, lease_owner=None)
                )
                if fence.rowcount != 1:
                    raise GoogleProblem("sync_lease_lost", 409)
                db.execute(delete(GmailMessage))
                db.add_all(GmailMessage(id=m["id"], payload=json.dumps(m)) for m in staged)
                row = db.get(GmailConnection, 1)
                row.credentials = self.vault.encrypt(values)
                row.history_id = checkpoint
                row.state, row.error, row.failures = "connected", None, 0
                row.last_success, row.next_sync = int(time.time()), int(time.time()) + 600
                db.commit()
        except Exception as error:
            problem = (
                error if isinstance(error, GoogleProblem) else GoogleProblem("provider_unavailable")
            )
            with Session(self.engine) as db:
                row = db.get(GmailConnection, 1)
                if row and row.lease_owner == owner:
                    row.credentials = self.vault.encrypt(values)
                    row.state = "expired" if problem.code == "reauthorization_required" else "error"
                    row.error = problem.code
                    row.failures += 1
                    row.next_sync = int(time.time()) + min(3600, 60 * 2 ** min(row.failures, 6))
                    row.lease_owner, row.lease_until = None, 0
                    db.commit()
            raise problem from None
        return self.status()
