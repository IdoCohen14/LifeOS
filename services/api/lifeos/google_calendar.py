import base64
import hashlib
import json
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote, urlencode, urlparse

import httpx
from sqlalchemy import LargeBinary, cast, delete, func, select, update
from sqlalchemy.orm import Session

from .credential_vault import CredentialVault
from .data_lock import runtime_lock
from .google_models import GoogleCalendar, GoogleConnection, GoogleOAuthState, GoogleRecord
from .models import LoginSession
from .schemas import instant
from .security import token_hash

SCOPES = [
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/calendar.events.readonly",
]
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/calendar/v3"
MAX_SYNC_BYTES = 32 * 1024 * 1024
MAX_CACHE_BYTES = 32 * 1024 * 1024
MAX_SYNC_SECONDS = 120


class GoogleProblem(Exception):
    def __init__(self, code, status=502):
        self.code, self.status = code, status


class GoogleCalendarService:
    Connection = GoogleConnection
    OAuthState = GoogleOAuthState
    Cache = GoogleCalendar
    scopes = SCOPES
    state_prefix = ""

    def __init__(self, engine, directory):
        self.engine = engine
        self.vault = CredentialVault(directory)
        self.http = httpx.Client(timeout=15, follow_redirects=False)

    def _request(self, method, url, *, max_bytes=16 * 1024 * 1024, **kwargs):
        try:
            target = urlparse(url)
            allowed = (
                target.scheme == "https"
                and target.hostname
                in {"www.googleapis.com", "gmail.googleapis.com", "oauth2.googleapis.com"}
                and target.port in (None, 443)
                and not target.username
                and not target.password
                and not target.fragment
                and method in {"GET", "POST"}
                and (method != "POST" or url == TOKEN_URL)
            )
        except ValueError:
            allowed = False
        if not allowed:
            raise GoogleProblem("invalid_provider_endpoint")
        headers = {**kwargs.pop("headers", {}), "Accept-Encoding": "identity"}
        started = time.monotonic()
        with self.http.stream(
            method, url, headers=headers, follow_redirects=False, timeout=15, **kwargs
        ) as response:
            if response.is_redirect:
                raise GoogleProblem("provider_redirect_rejected")
            if response.headers.get("content-encoding", "identity").strip().lower() != "identity":
                raise GoogleProblem("compressed_provider_response")
            if time.monotonic() - started > 30:
                raise GoogleProblem("provider_response_timeout")
            body = bytearray()
            # Count streamed bytes rather than trusting Content-Length; do not decompress.
            # Check each received chunk: coalescing would hide a slow trickle from the deadline.
            for chunk in response.iter_bytes():
                if len(body) + len(chunk) > max_bytes:
                    raise GoogleProblem("provider_response_too_large")
                if time.monotonic() - started > 30:
                    raise GoogleProblem("provider_response_timeout")
                body.extend(chunk)
            if time.monotonic() - started > 30:
                raise GoogleProblem("provider_response_timeout")
            return httpx.Response(
                response.status_code,
                headers=response.headers,
                content=bytes(body),
                request=response.request,
            )

    def connection(self, db):
        row = db.get(self.Connection, 1)
        if row is None:
            row = self.Connection(id=1)
            db.add(row)
            db.flush()
        return row

    def unlocked(self, row):
        if row.lease_owner and row.lease_until > int(time.time()):
            raise GoogleProblem("sync_in_progress", 409)

    def clear_cache(self, db):
        db.execute(delete(self.Cache))

    def secrets(self, row):
        try:
            return self.vault.decrypt(row.credentials) if row.credentials else {}
        except Exception:
            raise GoogleProblem("credentials_unavailable", 409) from None

    def status(self):
        with Session(self.engine) as db:
            row = db.get(self.Connection, 1)
            calendars = db.scalars(select(GoogleCalendar)).all()
            return {
                "configured": bool(row and row.credentials),
                "connected": bool(row and row.state in ("connected", "error", "syncing")),
                "state": row.state if row else "disconnected",
                "error": row.error if row else None,
                "last_success": row.last_success if row else None,
                "next_sync": row.next_sync if row else None,
                "syncing": bool(row and row.lease_owner and row.lease_until > int(time.time())),
                "stale": bool(
                    row and row.last_success and int(time.time()) - row.last_success > 1800
                ),
                "calendars": [
                    {"id": c.id, "name": c.name, "timezone": c.timezone, "selected": c.selected}
                    for c in calendars
                ],
                "window_days": {"past": 30, "future": 365},
            }

    def configure(self, client_id, client_secret):
        with Session(self.engine) as db:
            row = self.connection(db)
            self.unlocked(row)
            row.credentials = self.vault.encrypt(
                {"client_id": client_id, "client_secret": client_secret}
            )
            row.state = "configured"
            row.error = None
            row.last_success = None
            row.next_sync = 0
            row.lease_owner = None
            db.execute(delete(self.OAuthState))
            self.clear_cache(db)
            db.commit()

    def authorize(self, session_hash, origin):
        state = self.state_prefix + secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        redirect = origin + "/api/integrations/google/callback"
        with Session(self.engine) as db:
            row = self.connection(db)
            self.unlocked(row)
            values = self.secrets(row)
            if not values.get("client_id"):
                raise GoogleProblem("not_configured", 409)
            db.execute(delete(self.OAuthState))
            db.add(
                self.OAuthState(
                    state_hash=token_hash(state),
                    session_hash=session_hash,
                    verifier=self.vault.encrypt({"verifier": verifier}),
                    redirect_uri=redirect,
                    expires=int(time.time()) + 600,
                )
            )
            db.commit()
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
            {
                "client_id": values["client_id"],
                "redirect_uri": redirect,
                "response_type": "code",
                "scope": " ".join(self.scopes),
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "access_type": "offline",
                "prompt": "consent",
            }
        )

    def token_request(self, values, form):
        response = self._request(
            "POST",
            TOKEN_URL,
            max_bytes=128 * 1024,
            data={
                **form,
                "client_id": values["client_id"],
                "client_secret": values["client_secret"],
            },
        )
        if response.status_code in (400, 401):
            raise GoogleProblem("reauthorization_required", 409)
        if not response.is_success:
            raise GoogleProblem("provider_unavailable")
        result = response.json()
        if not result.get("access_token"):
            raise GoogleProblem("invalid_provider_response")
        granted = set(result.get("scope", " ".join(self.scopes)).split())
        if not set(self.scopes) <= granted:
            raise GoogleProblem("insufficient_scope", 409)
        return {
            **values,
            **{k: result[k] for k in ("access_token", "refresh_token") if result.get(k)},
            "expires_at": int(time.time()) + int(result.get("expires_in", 3600)),
        }

    def callback(self, state, code, error):
        with Session(self.engine) as db:
            saved = db.get(self.OAuthState, token_hash(state))
            if saved is None or saved.expires <= int(time.time()):
                raise GoogleProblem("invalid_oauth_state", 400)
            session = db.get(LoginSession, saved.session_hash)
            if not session or session.expires <= int(time.time()):
                raise GoogleProblem("invalid_oauth_state", 400)
            verifier = self.vault.decrypt(saved.verifier)["verifier"]
            redirect = saved.redirect_uri
            consumed = db.execute(
                delete(self.OAuthState).where(self.OAuthState.state_hash == saved.state_hash)
            )
            if consumed.rowcount != 1:
                raise GoogleProblem("invalid_oauth_state", 400)
            row = self.connection(db)
            self.unlocked(row)
            values = self.secrets(row)
            baseline = row.credentials
            session_hash = saved.session_hash
            db.commit()
        if error or not code:
            raise GoogleProblem("consent_cancelled", 400)
        values = self.token_request(
            {k: values[k] for k in ("client_id", "client_secret")},
            {
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": redirect,
                "grant_type": "authorization_code",
            },
        )
        if not values.get("refresh_token"):
            raise GoogleProblem("reauthorization_required", 409)
        with Session(self.engine) as db:
            row = self.connection(db)
            self.unlocked(row)
            session = db.get(LoginSession, session_hash)
            if row.credentials != baseline or not session or session.expires <= int(time.time()):
                raise GoogleProblem("invalid_oauth_state", 400)
            row.credentials = self.vault.encrypt(values)
            row.state = "connected"
            row.error = None
            row.last_success = None
            row.failures = 0
            row.next_sync = int(time.time())
            self.clear_cache(db)
            db.commit()

    def disconnect(self):
        with Session(self.engine) as db:
            row = self.connection(db)
            self.unlocked(row)
            values = self.secrets(row)
            row.credentials = (
                self.vault.encrypt(
                    {k: values[k] for k in ("client_id", "client_secret") if k in values}
                )
                if values
                else None
            )
            row.state = "configured" if values else "disconnected"
            row.error = None
            row.last_success = None
            row.next_sync = 0
            row.lease_owner = None
            db.execute(delete(self.OAuthState))
            self.clear_cache(db)
            db.commit()

    def select(self, ids):
        with Session(self.engine) as db:
            self.unlocked(self.connection(db))
            calendars = db.scalars(select(GoogleCalendar)).all()
            if not set(ids) <= {c.id for c in calendars}:
                raise GoogleProblem("unknown_calendar", 422)
            for calendar in calendars:
                chosen = calendar.id in ids
                if chosen != calendar.selected:
                    db.execute(delete(GoogleRecord).where(GoogleRecord.calendar_id == calendar.id))
                    calendar.sync_token = None
                calendar.selected = chosen
            db.commit()

    def sync(self):
        with runtime_lock(self.vault.directory):
            return self._sync()

    def _sync(self):
        owner = secrets.token_hex(16)
        now = int(time.time())
        started = time.monotonic()
        downloaded = 0
        with Session(self.engine) as db:
            row = self.connection(db)
            values = self.secrets(row)
            if not values.get("refresh_token"):
                raise GoogleProblem("not_connected", 409)
            acquired = db.execute(
                update(GoogleConnection)
                .where(GoogleConnection.id == 1, GoogleConnection.lease_until <= now)
                .values(lease_owner=owner, lease_until=now + 300)
            )
            if acquired.rowcount != 1:
                raise GoogleProblem("sync_in_progress", 409)
            db.commit()

        def heartbeat():
            if time.monotonic() - started > MAX_SYNC_SECONDS:
                raise GoogleProblem("calendar_sync_timeout", 409)
            with Session(self.engine) as db:
                result = db.execute(
                    update(GoogleConnection)
                    .where(GoogleConnection.id == 1, GoogleConnection.lease_owner == owner)
                    .values(lease_until=int(time.time()) + 300)
                )
                db.commit()
                if result.rowcount != 1:
                    raise GoogleProblem("sync_lease_lost", 409)

        def get(path, params):
            nonlocal values, downloaded
            heartbeat()
            response = self._request(
                "GET",
                API + path,
                params=params,
                headers={"Authorization": "Bearer " + values["access_token"]},
            )
            downloaded += len(response.content)
            if downloaded > MAX_SYNC_BYTES:
                raise GoogleProblem("calendar_download_limit_exceeded", 409)
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
                downloaded += len(response.content)
                if downloaded > MAX_SYNC_BYTES:
                    raise GoogleProblem("calendar_download_limit_exceeded", 409)
            if response.status_code == 410:
                raise GoogleProblem("sync_token_expired", 410)
            if response.status_code == 429:
                raise GoogleProblem("rate_limited")
            if response.status_code == 403:
                try:
                    reasons = {
                        item.get("reason")
                        for item in response.json().get("error", {}).get("errors", [])
                    }
                except (ValueError, AttributeError, TypeError):
                    reasons = set()
                if reasons & {
                    "rateLimitExceeded",
                    "userRateLimitExceeded",
                    "dailyLimitExceeded",
                    "quotaExceeded",
                }:
                    raise GoogleProblem("rate_limited")
            if response.status_code in (401, 403):
                raise GoogleProblem("reauthorization_required", 409)
            if not response.is_success:
                raise GoogleProblem("provider_unavailable")
            return response.json()

        def pages(path, params):
            items = []
            page_token = None
            for _ in range(50):
                result = get(path, {**params, **({"pageToken": page_token} if page_token else {})})
                items.extend(result.get("items", []))
                if len(items) > 25000:
                    raise GoogleProblem("calendar_limit_exceeded", 409)
                page_token = result.get("nextPageToken")
                if not page_token:
                    return items, result.get("nextSyncToken")
            raise GoogleProblem("calendar_limit_exceeded", 409)

        try:
            if values.get("expires_at", 0) <= now + 60:
                values = self.token_request(
                    values,
                    {"refresh_token": values["refresh_token"], "grant_type": "refresh_token"},
                )
            discovered, _ = pages("/users/me/calendarList", {"maxResults": 250})
            if len(discovered) > 100:
                raise GoogleProblem("calendar_limit_exceeded", 409)
            with Session(self.engine) as db:
                cached_bytes = db.scalar(
                    select(
                        func.coalesce(
                            func.sum(func.length(cast(GoogleRecord.payload, LargeBinary))), 0
                        )
                    )
                )
                if cached_bytes > MAX_CACHE_BYTES:
                    raise GoogleProblem("calendar_cache_limit_exceeded", 409)
                existing = {
                    c.id: {"selected": c.selected, "token": c.sync_token}
                    for c in db.scalars(select(GoogleCalendar))
                }
                raw = {}
                for record in db.scalars(select(GoogleRecord).where(GoogleRecord.kind == "raw")):
                    raw.setdefault(record.calendar_id, {})[record.external_id] = json.loads(
                        record.payload
                    )
            window_start = datetime.now(timezone.utc) - timedelta(days=30)
            window_end = datetime.now(timezone.utc) + timedelta(days=365)
            staged = {}
            staged_bytes = 0
            for calendar in discovered:
                cid = calendar["id"]
                old = existing.get(cid, {})
                chosen = old.get("selected", bool(calendar.get("primary")))
                if not chosen:
                    continue
                path = "/calendars/" + quote(cid, safe="") + "/events"
                token = old.get("token")
                try:
                    changed, checkpoint = pages(
                        path,
                        {
                            "singleEvents": "false",
                            "showDeleted": "true",
                            "maxResults": 2500,
                            **({"syncToken": token} if token else {}),
                        },
                    )
                except GoogleProblem as problem:
                    if problem.code != "sync_token_expired":
                        raise
                    token = None
                    changed, checkpoint = pages(
                        path, {"singleEvents": "false", "showDeleted": "true", "maxResults": 2500}
                    )
                if not checkpoint:
                    raise GoogleProblem("invalid_provider_response")
                records = dict(raw.get(cid, {})) if token else {}
                for event in changed:
                    if event.get("status") == "cancelled":
                        records.pop(event["id"], None)
                    else:
                        records[event["id"]] = event
                if len(records) > 25000:
                    raise GoogleProblem("calendar_limit_exceeded", 409)
                visible = {}
                for event in records.values():
                    if event.get("recurringEventId"):
                        continue
                    if event.get("recurrence"):
                        instances, _ = pages(
                            path + "/" + quote(event["id"], safe="") + "/instances",
                            {
                                "timeMin": window_start.isoformat(),
                                "timeMax": window_end.isoformat(),
                                "showDeleted": "false",
                                "maxResults": 2500,
                            },
                        )
                    else:
                        instances = [event]
                    for instance in instances:
                        normalized = normalize_event(cid, instance)
                        if (
                            normalized
                            and normalized["end"][:10] >= window_start.date().isoformat()
                            and normalized["start"][:10] <= window_end.date().isoformat()
                        ):
                            visible[instance["id"]] = normalized
                encoded = []
                for kind, collection in [("raw", records), ("visible", visible)]:
                    for eid, payload in collection.items():
                        text = json.dumps(payload)
                        staged_bytes += len(text.encode("utf-8"))
                        if staged_bytes > MAX_CACHE_BYTES:
                            raise GoogleProblem("calendar_cache_limit_exceeded", 409)
                        encoded.append((kind, eid, text))
                staged[cid] = (encoded, checkpoint)
            heartbeat()
            with Session(self.engine) as db:
                fence = db.execute(
                    update(GoogleConnection)
                    .where(GoogleConnection.id == 1, GoogleConnection.lease_owner == owner)
                    .values(lease_until=int(time.time()) + 300)
                )
                if fence.rowcount != 1:
                    raise GoogleProblem("sync_lease_lost", 409)
                known = {calendar["id"] for calendar in discovered}
                for row in db.scalars(select(GoogleCalendar)):
                    if row.id not in known:
                        db.delete(row)
                for calendar in discovered:
                    cid = calendar["id"]
                    row = db.get(GoogleCalendar, cid)
                    if row is None:
                        row = GoogleCalendar(id=cid, selected=bool(calendar.get("primary")))
                        db.add(row)
                    row.name = calendar.get("summary", "Google Calendar")
                    row.timezone = calendar.get("timeZone", "UTC")
                    db.flush()
                    if cid in staged:
                        encoded, checkpoint = staged[cid]
                        db.execute(delete(GoogleRecord).where(GoogleRecord.calendar_id == cid))
                        for kind, eid, payload in encoded:
                            db.add(
                                GoogleRecord(
                                    calendar_id=cid,
                                    external_id=eid,
                                    kind=kind,
                                    payload=payload,
                                )
                            )
                        row.sync_token = checkpoint
                connection = db.get(GoogleConnection, 1)
                connection.credentials = self.vault.encrypt(values)
                connection.state = "connected"
                connection.error = None
                connection.last_success = int(time.time())
                connection.next_sync = int(time.time()) + 600
                connection.failures = 0
                connection.lease_owner = None
                connection.lease_until = 0
                db.flush()
                if time.monotonic() - started > MAX_SYNC_SECONDS:
                    raise GoogleProblem("calendar_sync_timeout", 409)
                db.commit()
        except Exception as error:
            problem = (
                error if isinstance(error, GoogleProblem) else GoogleProblem("provider_unavailable")
            )
            with Session(self.engine) as db:
                row = db.get(GoogleConnection, 1)
                if row and row.lease_owner == owner:
                    row.credentials = self.vault.encrypt(values)
                    row.state = "expired" if problem.code == "reauthorization_required" else "error"
                    row.error = problem.code
                    row.failures += 1
                    row.next_sync = int(time.time()) + min(3600, 60 * 2 ** min(row.failures, 6))
                    row.lease_owner = None
                    row.lease_until = 0
                    db.commit()
            raise problem from None
        return self.status()

    def events(self):
        with Session(self.engine) as db:
            records = db.scalars(
                select(GoogleRecord)
                .join(GoogleCalendar)
                .where(GoogleRecord.kind == "visible", GoogleCalendar.selected.is_(True))
            ).all()
            return [json.loads(record.payload) for record in records]


def normalize_event(calendar_id, event):
    if event.get("status") == "cancelled":
        return None
    start = event.get("start", {})
    end = event.get("end", {})
    all_day = "date" in start
    try:
        begin = (
            date.fromisoformat(start["date"]).isoformat() if all_day else instant(start["dateTime"])
        )
        finish = (
            date.fromisoformat(end["date"]).isoformat() if all_day else instant(end["dateTime"])
        )
        if (
            finish <= begin
            if all_day
            else datetime.fromisoformat(finish) <= datetime.fromisoformat(begin)
        ):
            raise ValueError()
    except (KeyError, ValueError):
        raise GoogleProblem("invalid_provider_response") from None
    link = event.get("htmlLink", "")
    host = urlparse(link).hostname or ""
    if urlparse(link).scheme != "https" or not (
        host == "google.com" or host.endswith(".google.com")
    ):
        link = ""
    eid = hashlib.sha256((calendar_id + "\0" + event["id"]).encode()).hexdigest()
    return {
        "id": "google-" + eid,
        "title": str(event.get("summary") or "(Google Calendar)")[:240],
        "notes": str(event.get("location") or "")[:10000],
        "start": begin,
        "end": finish,
        "all_day": all_day,
        "created_at": event.get("created", "1970-01-01T00:00:00Z"),
        "source": "google",
        "source_url": link,
        "provider_id": event["id"],
        "calendar_id": calendar_id,
        "updated_at": event.get("updated"),
    }
