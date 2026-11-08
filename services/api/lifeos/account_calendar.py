"""Account-scoped read-only Calendar discovery/delta/recurrence projection."""

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from .academic import begin_academic_write
from .account_providers import AccountProviders
from .google_calendar import API, GoogleCalendarService, GoogleProblem, normalize_event
from .models import AccountProvider, AccountProviderRecord


def cache_id(kind, calendar_id, external_id=""):
    return hashlib.sha256(json.dumps([kind, calendar_id, external_id]).encode()).hexdigest()


class AccountCalendar(AccountProviders):
    def calendars(self, account_id):
        return [
            {
                "id": row["calendar_id"],
                "name": row["name"],
                "timezone": row.get("timezone", "UTC"),
                "selected": row["selected"],
            }
            for row in self.records(account_id, "google")
            if row.get("kind") == "calendar"
        ]

    def select(self, account_id, ids):
        if (
            not isinstance(ids, list)
            or len(ids) > 100
            or any(not isinstance(id, str) for id in ids)
            or len(set(ids)) != len(ids)
        ):
            raise ValueError("Invalid calendar selection")
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, account_id)
            connection = db.get(AccountProvider, (account_id, "google"))
            if connection is None or connection.credentials is None:
                raise ValueError("Google not configured")
            rows = list(
                db.scalars(
                    select(AccountProviderRecord).where(
                        AccountProviderRecord.account_id == account_id,
                        AccountProviderRecord.provider == "google",
                    )
                )
            )
            decoded = [(row, json.loads(row.payload)) for row in rows]
            available = {
                value["calendar_id"] for _, value in decoded if value.get("kind") == "calendar"
            }
            if not set(ids) <= available:
                raise ValueError("Calendar selection changed")
            envelope = self.vault.decrypt(connection.credentials)
            if envelope.get("account_id") != account_id or envelope.get("provider") != "google":
                raise PermissionError("Credential owner mismatch")
            envelope["values"]["selected_calendars"] = ids
            connection.credentials = self.vault.encrypt(envelope)
            connection.revision += 1
            connection.lease_owner, connection.lease_until, connection.next_sync = None, 0, 0
            for row, value in decoded:
                if value.get("kind") == "calendar":
                    value["selected"] = value["calendar_id"] in ids
                    if not value["selected"]:
                        value["token"] = None
                    row.payload = json.dumps(value)
                elif value.get("calendar_id") not in ids:
                    db.delete(row)
            db.commit()
        return self.calendars(account_id)

    def events(self, account_id):
        return [
            row["payload"]
            for row in self.records(account_id, "google")
            if row.get("kind") == "visible"
        ]

    def sync(self, account_id, *, helper_factory=GoogleCalendarService):
        lease = self.begin_sync(account_id, "google")
        helper = None
        values = lease["credentials"]
        started = time.monotonic()
        downloaded = 0

        def get(path, params):
            nonlocal values, downloaded
            if time.monotonic() - started > 120:
                raise GoogleProblem("calendar_sync_timeout", 409)
            response = helper._request(
                "GET",
                API + path,
                params=params,
                headers={"Authorization": "Bearer " + values["access_token"]},
            )
            downloaded += len(response.content)
            if response.status_code == 401:
                values = helper.token_request(
                    values,
                    {"grant_type": "refresh_token", "refresh_token": values["refresh_token"]},
                )
                response = helper._request(
                    "GET",
                    API + path,
                    params=params,
                    headers={"Authorization": "Bearer " + values["access_token"]},
                )
                downloaded += len(response.content)
            if downloaded > 32 * 1024 * 1024 or time.monotonic() - started > 120:
                raise GoogleProblem("calendar_download_limit_exceeded", 409)
            if response.status_code == 410:
                raise GoogleProblem("sync_token_expired", 410)
            if response.status_code in (401, 403):
                raise GoogleProblem("reauthorization_required", 409)
            if response.status_code == 429:
                raise GoogleProblem("rate_limited")
            if not response.is_success:
                raise GoogleProblem("provider_unavailable")
            result = response.json()
            if not isinstance(result, dict) or not isinstance(result.get("items", []), list):
                raise GoogleProblem("invalid_provider_response")
            return result

        def pages(path, params):
            items = []
            page = None
            for _ in range(50):
                result = get(path, {**params, **({"pageToken": page} if page else {})})
                items.extend(result.get("items", []))
                if len(items) > 25000:
                    raise GoogleProblem("calendar_limit_exceeded", 409)
                page = result.get("nextPageToken")
                if not page:
                    return items, result.get("nextSyncToken")
            raise GoogleProblem("calendar_limit_exceeded", 409)

        try:
            helper = helper_factory(self.engine, self.vault.directory)
            if not values.get("refresh_token"):
                raise GoogleProblem("not_connected", 409)
            if values.get("expires_at", 0) <= int(time.time()) + 60:
                values = helper.token_request(
                    values,
                    {"grant_type": "refresh_token", "refresh_token": values["refresh_token"]},
                )
            discovered, _ = pages("/users/me/calendarList", {"maxResults": 250})
            if len(discovered) > 100:
                raise GoogleProblem("calendar_limit_exceeded", 409)
            cached = self.records(account_id, "google")
            old_calendars = {
                row["calendar_id"]: row for row in cached if row.get("kind") == "calendar"
            }
            old_raw = {}
            for row in cached:
                if row.get("kind") == "raw":
                    old_raw.setdefault(row["calendar_id"], {})[row["external_id"]] = row["payload"]
            selected = values.get("selected_calendars")
            if selected is not None and (
                not isinstance(selected, list) or any(not isinstance(id, str) for id in selected)
            ):
                raise ValueError("Invalid calendar selection")
            window_start = datetime.now(timezone.utc) - timedelta(days=30)
            window_end = datetime.now(timezone.utc) + timedelta(days=365)
            staged = []
            for calendar in discovered:
                cid = calendar.get("id")
                if not isinstance(cid, str) or not 1 <= len(cid) <= 1024:
                    raise GoogleProblem("invalid_provider_response")
                chosen = cid in selected if selected is not None else bool(calendar.get("primary"))
                entry = {
                    "id": cache_id("calendar", cid),
                    "kind": "calendar",
                    "calendar_id": cid,
                    "name": str(calendar.get("summary", "Google Calendar"))[:240],
                    "timezone": calendar.get("timeZone", "UTC"),
                    "selected": chosen,
                    "token": None,
                }
                staged.append(entry)
                if not chosen:
                    continue
                path = "/calendars/" + quote(cid, safe="") + "/events"
                token = old_calendars.get(cid, {}).get("token")
                params = {"singleEvents": "false", "showDeleted": "true", "maxResults": 2500}
                try:
                    changed, checkpoint = pages(
                        path, {**params, **({"syncToken": token} if token else {})}
                    )
                except GoogleProblem as error:
                    if error.code != "sync_token_expired":
                        raise
                    token = None
                    changed, checkpoint = pages(path, params)
                if not isinstance(checkpoint, str) or not checkpoint:
                    raise GoogleProblem("invalid_provider_response")
                entry["token"] = checkpoint
                raw = dict(old_raw.get(cid, {})) if token else {}
                for event in changed:
                    if event.get("status") == "cancelled":
                        raw.pop(event["id"], None)
                    else:
                        raw[event["id"]] = event
                if len(raw) > 25000:
                    raise GoogleProblem("calendar_limit_exceeded", 409)
                visible = {}
                for event in raw.values():
                    if event.get("recurringEventId"):
                        continue
                    instances, _ = (
                        pages(
                            path + "/" + quote(event["id"], safe="") + "/instances",
                            {
                                "timeMin": window_start.isoformat(),
                                "timeMax": window_end.isoformat(),
                                "showDeleted": "false",
                                "maxResults": 2500,
                            },
                        )
                        if event.get("recurrence")
                        else ([event], None)
                    )
                    for instance in instances:
                        normalized = normalize_event(cid, instance)
                        if (
                            normalized
                            and normalized["end"][:10] >= window_start.date().isoformat()
                            and normalized["start"][:10] <= window_end.date().isoformat()
                        ):
                            visible[instance["id"]] = normalized
                for kind, collection in [("raw", raw), ("visible", visible)]:
                    staged.extend(
                        {
                            "id": cache_id(kind, cid, eid),
                            "kind": kind,
                            "calendar_id": cid,
                            "external_id": eid,
                            "payload": payload,
                        }
                        for eid, payload in collection.items()
                    )
            self.commit_sync(
                account_id, "google", lease["owner"], lease["revision"], staged, credentials=values
            )
        except Exception as error:
            self.abort_sync(
                account_id,
                "google",
                lease["owner"],
                lease["revision"],
                error=getattr(error, "code", "provider_unavailable"),
            )
            raise
        finally:
            if helper is not None:
                helper.http.close()
        return self.status(account_id, "google")
