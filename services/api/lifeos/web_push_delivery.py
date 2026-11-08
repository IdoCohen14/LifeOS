"""Bounded cached-only Push eligibility and durable device/version delivery claims."""

import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from .assistant import day_boundary, scoped_settings
from .briefings import BriefingService, stale_sources
from .data_lock import _file_lock
from .models import Settings
from .notification_models import NotificationAction, NotificationPreferences, NotificationRead
from .notifications import Preferences
from .push_copy import notification_copy, with_owned_course
from .recommendations import RecommendationService, stable_id
from .web_push import WebPushService
from .web_push_models import PushDelivery
from .web_push_transport import send_push


def current_time():
    return datetime.now(timezone.utc)


def check_deadline(deadline):
    if time.monotonic() >= deadline:
        raise HTTPException(503, "push_resource_limit")


def quiet_now(prefs, now, zone):
    local = now.astimezone(ZoneInfo(zone)).strftime("%H:%M")
    start, end = prefs.quiet_start, prefs.quiet_end
    return prefs.quiet_enabled and (
        start == end or (start <= local < end if start < end else local >= start or local < end)
    )


def delivery_key(device, item):
    return stable_id("push", [device[0], device[1], item["id"], item.get("snoozed_until") or 0])


def cached_feed(engine, deadline=None, *, device=None):
    deadline = min(time.monotonic() + 10, deadline if deadline is not None else float("inf"))
    check_deadline(deadline)

    recommendation = RecommendationService(engine, None, None, None, deadline=deadline)
    candidates, _ = recommendation.candidates()
    candidates += BriefingService(engine).candidates()
    check_deadline(deadline)
    candidates.sort(key=lambda item: (item["priority"], item["order"], item["id"]))
    now = current_time()
    with Session(engine) as db:
        db.execute(text("BEGIN"))
        settings = db.get(Settings, 1)
        row = db.get(NotificationPreferences, 1)
        prefs = Preferences.model_validate(row) if row else Preferences()
        stale = stale_sources(db, now)
        items = []
        for offset in range(0, len(candidates), 500):
            check_deadline(deadline)
            batch = candidates[offset : offset + 500]
            ids = [item["id"] for item in batch]
            reads = set(db.scalars(select(NotificationRead.id).where(NotificationRead.id.in_(ids))))
            actions = {
                row.id: row
                for row in db.scalars(
                    select(NotificationAction).where(NotificationAction.id.in_(ids))
                )
            }
            eligible = []
            for item in batch:
                check_deadline(deadline)
                kind = item.get("kind", "due_soon")
                allowed = (
                    prefs.briefings
                    if kind.endswith("_briefing")
                    else prefs.conflicts
                    if kind == "conflict"
                    else prefs.tasks
                )
                action = actions.get(item["id"])
                if (
                    item["id"] in reads
                    or not prefs.enabled
                    or not allowed
                    or (
                        action
                        and (action.dismissed or (action.snoozed_until or 0) > now.timestamp())
                    )
                ):
                    continue
                eligible.append(
                    {
                        **item,
                        "read": False,
                        "snoozed_until": action.snoozed_until if action else None,
                    }
                )
            excluded = set()
            if device:
                delivery_ids = [delivery_key(device, item) for item in eligible]
                excluded = set(
                    db.scalars(
                        select(PushDelivery.id).where(
                            PushDelivery.id.in_(delivery_ids),
                            (PushDelivery.sent.is_(True))
                            | (PushDelivery.attempts >= 3)
                            | (PushDelivery.next_attempt > now.timestamp()),
                        )
                    )
                )
            items.extend(
                item
                for item in eligible
                if not device or delivery_key(device, item) not in excluded
            )
            if len(items) >= 20:
                break
        check_deadline(deadline)
        return {
            "items": items[:20],
            "quiet": quiet_now(prefs, now, settings.timezone),
            "preferences": prefs.model_dump(),
            "stale_sources": stale,
        }


class PushDeliveryService(WebPushService):
    def __init__(self, engine, directory, *, feed=None, sender=None, account_id=None):
        super().__init__(engine, directory, account_id=account_id)
        from .web_push_models import AccountPushDelivery

        self.delivery_model = AccountPushDelivery if account_id is not None else PushDelivery
        self.feed = feed
        self.sender = sender or self.send_default
        self.injected_sender = sender is not None

    def send_default(self, subscription, key, contact, payload):
        from urllib.parse import urlsplit

        from .web_push_transport import valid_endpoint

        target = urlsplit(valid_endpoint(subscription["endpoint"]))
        if target.hostname.endswith(".push.apple.com"):
            headers = self.apple_vapid_headers(key, contact, "https://" + target.hostname)
            return send_push(subscription, key, contact, payload, vapid_headers=headers)
        return send_push(subscription, key, contact, payload)

    def read_feed(self, deadline, device=None):
        check_deadline(deadline)
        if self.account_id is not None and self.feed is None:
            from .account_notices import AccountNotices

            result = AccountNotices(self.engine).feed(self.account_id)
            check_deadline(deadline)
            return result
        result = (
            self.feed()
            if self.feed is not None
            else cached_feed(self.engine, deadline, device=device)
        )
        check_deadline(deadline)
        return result

    def run_due(self):
        # Fixture browser/server processes can never accidentally send to real providers.
        if os.environ.get("LIFEOS_TEST_MODE") == "1" and not self.injected_sender:
            return 0
        try:
            with _file_lock(self.directory / ".lifeos-push.lock", error="push_busy"):
                return self._run_locked()
        except RuntimeError:
            return 0

    def _run_locked(self):
        now = current_time().timestamp()
        deadline = time.monotonic() + 20
        PushConfig, PushDevice = self.models
        PushDelivery = self.delivery_model
        with Session(self.engine) as db:
            self.authorize(db)
            db.execute(text("BEGIN IMMEDIATE"))
            db.execute(
                delete(PushDevice).where(
                    self.device_scope(PushDevice), PushDevice.last_seen < now - 90 * 86400
                )
            )
            db.execute(
                delete(PushDelivery).where(
                    PushDelivery.device_id.in_(
                        select(PushDevice.id).where(self.device_scope(PushDevice))
                    ),
                    PushDelivery.created_at < now - 30 * 86400,
                )
            )
            if db.get(PushConfig, self.config_id) is None:
                db.commit()
                return 0
            devices = list(
                db.execute(
                    select(PushDevice.id, PushDevice.generation)
                    .where(
                        self.device_scope(PushDevice),
                        PushDevice.enabled.is_(True),
                        PushDevice.cooldown_until <= now,
                    )
                    .limit(5)
                )
            )
            db.commit()
        attempts = 0
        for id, generation in devices:
            if time.monotonic() >= deadline:
                break
            feed = self.read_feed(deadline, (id, generation))
            if (
                feed["quiet"]
                or feed.get("stale_sources")
                or not feed.get("preferences", {"enabled": True}).get("enabled", True)
            ):
                continue
            for item in feed["items"]:
                if item["read"] or (item.get("snoozed_until") or 0) > current_time().timestamp():
                    continue
                check_deadline(deadline)
                claimed = self.claim(id, item, deadline=deadline)
                if claimed is None:
                    continue
                device_generation, delivery_id, subscription, key, contact, payload = claimed
                check_deadline(deadline)
                try:
                    code, retry = self.sender(subscription, key, contact, payload)
                except Exception:
                    code, retry = 0, 300
                self.outcome(id, device_generation, delivery_id, code, retry)
                attempts += 1
                break
        return attempts

    def claim(self, device_id, item, *, deadline=None):
        deadline = deadline if deadline is not None else time.monotonic() + 20
        check_deadline(deadline)
        now = current_time()
        PushConfig, PushDevice = self.models
        PushDelivery = self.delivery_model
        with Session(self.engine) as db:
            self.authorize(db)
            db.execute(text("BEGIN IMMEDIATE"))
            device, config, settings = (
                db.get(PushDevice, device_id),
                db.get(PushConfig, self.config_id),
                scoped_settings(db, self.account_id),
            )
            if (
                not device
                or self.account_id is not None
                and device.account_id != self.account_id
                or not config
                or not device.enabled
                or device.cooldown_until > now.timestamp()
            ):
                return None
            if self.account_id is not None:
                from .account_preferences import AccountPreferences

                prefs = Preferences.model_validate(
                    AccountPreferences(self.engine).get(self.account_id, "notifications")["values"]
                )
            else:
                row = db.get(NotificationPreferences, 1)
                prefs = Preferences.model_validate(row) if row else Preferences()
            start, end = prefs.quiet_start, prefs.quiet_end
            delivery_id = stable_id(
                "push", [device.id, device.generation, item["id"], item.get("snoozed_until") or 0]
            )
            delivery = db.get(PushDelivery, delivery_id)
            if delivery and (
                delivery.sent or delivery.attempts >= 3 or delivery.next_attempt > now.timestamp()
            ):
                return None
            fresh = self.read_feed(deadline, (device.id, device.generation))
            if (
                fresh["quiet"]
                or fresh.get("stale_sources")
                or not any(
                    not value["read"]
                    and value["id"] == item["id"]
                    and (value.get("snoozed_until") or 0) == (item.get("snoozed_until") or 0)
                    for value in fresh["items"]
                )
            ):
                return None
            # The writer transaction fences source changes until this claim is committed.
            if quiet_now(prefs, current_time(), settings.timezone):
                return None
            if self.account_id is not None:
                from .secretary_preferences import secretary_preferences

                controls, _ = secretary_preferences(db, self.account_id)
                if controls.push_daily_limit:
                    now = current_time()
                    day = now.astimezone(ZoneInfo(settings.timezone)).date()
                    left = day_boundary(day.isoformat(), ZoneInfo(settings.timezone)).timestamp()
                    right = day_boundary(
                        (day + timedelta(days=1)).isoformat(), ZoneInfo(settings.timezone)
                    ).timestamp()
                    reserved = delivery is not None and left <= delivery.created_at < right
                    count = db.scalar(
                        select(func.count())
                        .select_from(PushDelivery)
                        .where(
                            PushDelivery.device_id == device.id,
                            PushDelivery.created_at >= left,
                            PushDelivery.created_at < right,
                        )
                    )
                    if count >= controls.push_daily_limit and not reserved:
                        return None
                    if delivery is not None and not reserved:
                        delivery.created_at = now.timestamp()
            if delivery is None:
                delivery = PushDelivery(
                    id=delivery_id,
                    device_id=device.id,
                    created_at=now.timestamp(),
                    attempts=0,
                    next_attempt=0,
                    sent=False,
                )
                db.add(delivery)
            subscription = self.open(device.subscription)
            if (
                subscription.get("expirationTime") is not None
                and subscription["expirationTime"] <= now.timestamp() * 1000
            ):
                db.delete(device)
                db.commit()
                return None
            key = self.open(config.private_key)["key"]
            delivery.attempts += 1
            delivery.next_attempt = now.timestamp() + 300
            device.cooldown_until = now.timestamp() + 300
            # Preserve this new claim even if a fixture clock makes creation timestamps equal.
            db.flush()
            retained = (
                select(PushDelivery.id)
                .where(PushDelivery.device_id == device_id, PushDelivery.id != delivery_id)
                .order_by(PushDelivery.created_at.desc(), PushDelivery.id.desc())
                .limit(499)
            )
            db.execute(
                delete(PushDelivery).where(
                    PushDelivery.device_id == device_id,
                    PushDelivery.id != delivery_id,
                    PushDelivery.id.not_in(retained),
                )
            )
            result = (
                device.generation,
                delivery_id,
                subscription,
                key,
                config.contact,
                {
                    "id": delivery_id,
                    "language": settings.language,
                    "zone": settings.timezone,
                    "quiet_enabled": prefs.quiet_enabled,
                    "quiet_start": start,
                    "quiet_end": end,
                    "expires": int(now.timestamp()) + 300,
                    **notification_copy(
                        with_owned_course(
                            db,
                            self.account_id,
                            next(value for value in fresh["items"] if value["id"] == item["id"]),
                        ),
                        settings.language,
                        settings.timezone,
                        now,
                    ),
                },
            )
            check_deadline(deadline)
            db.commit()
            return result

    def outcome(self, device_id, generation, delivery_id, code, retry):
        now = current_time().timestamp()
        PushConfig, PushDevice = self.models
        PushDelivery = self.delivery_model
        with Session(self.engine) as db:
            self.authorize(db)
            db.execute(text("BEGIN IMMEDIATE"))
            device, delivery = db.get(PushDevice, device_id), db.get(PushDelivery, delivery_id)
            if (
                not device
                or self.account_id is not None
                and device.account_id != self.account_id
                or device.generation != generation
                or not delivery
                or delivery.device_id != device_id
            ):
                return
            if code in (404, 410):
                db.delete(device)
            elif 200 <= code <= 202:
                delivery.sent = True
                device.cooldown_until, device.last_error = now + 900, None
            else:
                delivery.next_attempt = now + min(3600, max(300, retry))
                device.cooldown_until = delivery.next_attempt
                device.last_error = "push_unavailable"
                if 300 <= code < 500 and code != 429:
                    device.enabled, device.last_error = False, "push_rejected"
            db.commit()
