"""Owned deterministic recommendation/notification feed and local receipt state."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .academic import begin_academic_write
from .account_briefings import AccountBriefings
from .account_mail import AccountMail
from .account_moodle_changes import AccountMoodleChanges
from .account_preferences import AccountPreferences
from .account_snapshot import AccountSnapshot
from .class_reminders import class_room, is_class_event
from .models import AccountNoticeState, AccountProvider
from .notifications import ActionInput, ReadInput
from .push_copy import with_owned_course
from .recommendations import RecommendationService, stable_id


class AccountNotices(AccountSnapshot):
    def stale_sources(self, account_id, *, mail=False):
        names = {
            "google": "Google Calendar",
            "moodle": "Moodle",
            "braude": "Braude",
            **({"gmail": "Gmail"} if mail else {}),
        }
        now = int(datetime.now(timezone.utc).timestamp())
        with Session(self.engine) as db:
            self.authorize(db, account_id)
            return [
                names[row.provider]
                for row in db.scalars(
                    select(AccountProvider).where(
                        AccountProvider.account_id == account_id,
                        AccountProvider.provider.in_(names),
                    )
                )
                if row.credentials
                and (row.error or row.last_success is not None and row.last_success < now - 1800)
            ]

    def candidates(self, account_id):
        from .account_requests import AccountRequests

        snapshot = self.build(account_id)
        items, limited = RecommendationService(self.engine, None, None, None).candidates(
            snapshot=snapshot
        )
        prefs = AccountPreferences(self.engine).get(account_id, "notifications")["values"]
        from .secretary_preferences import secretary_preferences

        with Session(self.engine) as db:
            controls, _ = secretary_preferences(db, account_id)
        if prefs["tasks"]:
            items.extend(AccountRequests(self.engine).candidates(account_id))
        items.extend(AccountMoodleChanges(self.engine).candidates(account_id))
        if prefs["briefings"]:
            items.extend(AccountBriefings(self.engine).candidates(account_id))
        if prefs["mail"]:
            mail = AccountMail(self.engine).get(account_id)
            items.extend(
                {
                    "id": stable_id("new_mail", [mail["revision"], row["id"]]),
                    "kind": "new_mail",
                    "title": row["subject"],
                    "source_ids": [row["id"]],
                    "source": "Gmail",
                    "target": "dashboard",
                    "priority": 3,
                    "order": str(row["received_at"]),
                }
                for row in mail["queue"]
            )
        if prefs["events"] or controls.class_reminder_minutes:
            now = datetime.now(timezone.utc)
            zone = ZoneInfo(snapshot["settings"]["timezone"])
            today = now.astimezone(zone).date()
            for event in snapshot["events"]:
                if event.get("source") == "assignment":
                    continue
                lesson = is_class_event(event)
                if lesson:
                    start = datetime.fromisoformat(event["start"].replace("Z", "+00:00"))
                    upcoming = bool(controls.class_reminder_minutes) and now < start <= now + timedelta(minutes=controls.class_reminder_minutes)
                elif not prefs["events"]:
                    continue
                else:
                    upcoming = None
                upcoming = upcoming if upcoming is not None else (
                    today.isoformat() <= event["start"] <= (today + timedelta(days=1)).isoformat()
                    if event["all_day"]
                    else now
                    <= datetime.fromisoformat(event["start"].replace("Z", "+00:00"))
                    < now + timedelta(hours=24)
                )
                if upcoming:
                    items.append(
                        {
                            "id": stable_id("class_reminder", [event.get("source"), event["id"], event["start"]]) if lesson else stable_id(
                                "upcoming_event",
                                [
                                    event.get("source", "personal"),
                                    event["id"],
                                    event["title"],
                                    event["start"],
                                    event["end"],
                                    zone.key,
                                ],
                            ),
                            "kind": "upcoming_event",
                            "event_source": event.get("source", "personal"),
                            "title": event["title"],
                            "start": event["start"],
                            "end": event["end"],
                            "all_day": event["all_day"],
                            "target": "timetable" if lesson else "calendar",
                            **({"lesson": True, "course_id": event.get("course_id"), "class_room": class_room(event)} if lesson else {}),
                            "source_ids": [event["id"]],
                            "priority": -1 if lesson else 3,
                            "order": event["start"],
                        }
                    )
        return (
            sorted(items, key=lambda row: (row["priority"], row["order"], row["id"])),
            limited,
            snapshot,
            prefs,
        )

    def states(self, db, account_id, ids):
        result = {}
        for offset in range(0, len(ids), 500):
            for row in db.scalars(
                select(AccountNoticeState).where(
                    AccountNoticeState.account_id == account_id,
                    AccountNoticeState.id.in_(ids[offset : offset + 500]),
                )
            ):
                result[row.id] = row
        return result

    def recommendations(self, account_id):
        snapshot = self.build(account_id)
        items, limited = RecommendationService(self.engine, None, None, None).candidates(
            snapshot=snapshot
        )
        now = int(datetime.now(timezone.utc).timestamp())
        with Session(self.engine) as db:
            self.authorize(db, account_id)
            states = self.states(db, account_id, [row["id"] for row in items])
            visible = [
                row
                for row in items
                if not states.get(row["id"]) or (states[row["id"]].recommendation_until or 0) <= now
            ]
        return {
            "items": visible[:5],
            "truncated": limited or len(visible) > 5,
            "stale_sources": self.stale_sources(account_id),
        }

    def feed(self, account_id):
        items, limited, snapshot, prefs = self.candidates(account_id)
        now = int(datetime.now(timezone.utc).timestamp())
        local = (
            datetime.now(timezone.utc)
            .astimezone(ZoneInfo(snapshot["settings"]["timezone"]))
            .strftime("%H:%M")
        )
        start, end = prefs["quiet_start"], prefs["quiet_end"]
        quiet = prefs["quiet_enabled"] and (
            start == end or (start <= local < end if start < end else local >= start or local < end)
        )
        visible = []
        hidden = []
        with Session(self.engine) as db:
            self.authorize(db, account_id)
            states = self.states(db, account_id, [row["id"] for row in items])
            for item in items:
                category = (
                    "conflicts"
                    if item["kind"] == "conflict"
                    else "briefings"
                    if item["kind"] in ("daily_briefing", "weekly_briefing")
                    else "mail"
                    if item["kind"] == "new_mail"
                    else "enabled" if item.get("lesson") else "events"
                    if item["kind"] == "upcoming_event"
                    else "tasks"
                )
                if not prefs["enabled"] or not prefs[category]:
                    continue
                row = states.get(item["id"])
                value = {
                    **item,
                    "read": bool(row and row.read_at is not None),
                    "dismissed": bool(row and row.dismissed),
                    "snoozed_until": row.snoozed_until if row else None,
                }
                (
                    hidden if value["dismissed"] or (value["snoozed_until"] or 0) > now else visible
                ).append(value)
        visible.sort(key=lambda row: row["read"])
        with Session(self.engine) as db:
            self.authorize(db, account_id)
            synced = dict(db.execute(select(AccountProvider.provider, AccountProvider.last_success).where(
                AccountProvider.account_id == account_id
            )).all())

            def contextual(rows):
                result = []
                for item in rows[:20]:
                    value = with_owned_course(db, account_id, item)
                    provider = "moodle" if item["kind"] == "moodle_update" else "gmail" if item["kind"] == "new_mail" else item.get("event_source")
                    if synced.get(provider) is not None:
                        value = {**value, "source_updated_at": synced[provider]}
                    result.append(value)
                return result

            visible_items, hidden_items = contextual(visible), contextual(hidden)
        return {
            "items": visible_items,
            "hidden": hidden_items,
            "hidden_total": len(hidden),
            "hidden_truncated": len(hidden) > 20,
            "unread": sum(not row["read"] for row in visible),
            "truncated": len(visible) > 20,
            "conflicts_limited": limited,
            "quiet": quiet,
            "preferences": prefs,
            "stale_sources": self.stale_sources(account_id, mail=prefs["mail"]),
        }

    def mutate(self, account_id, *, read_ids=None, action=None, dismiss_recommendation=None):
        feed = self.feed(account_id)
        visible = {row["id"] for row in feed["items"]}
        hidden = {row["id"] for row in feed["hidden"]}
        now = int(datetime.now(timezone.utc).timestamp())
        if read_ids is not None:
            ids = ReadInput(ids=read_ids).ids
            if not set(ids) <= visible:
                raise LookupError("Notifications changed")
        elif action is not None:
            action = ActionInput.model_validate(action)
            ids = [action.id]
            if action.id not in visible | hidden:
                raise LookupError("Notification not found")
        elif dismiss_recommendation is not None:
            ids = [dismiss_recommendation]
            if dismiss_recommendation not in {
                row["id"] for row in self.recommendations(account_id)["items"]
            }:
                raise LookupError("Recommendation not found")
        else:
            raise ValueError("Missing action")
        with Session(self.engine) as db:
            begin_academic_write(db)
            self.authorize(db, account_id)
            for id in ids:
                row = db.get(AccountNoticeState, (account_id, id))
                if row is None:
                    row = AccountNoticeState(account_id=account_id, id=id, dismissed=False)
                    db.add(row)
                row.updated_at = now
                if read_ids is not None:
                    row.read_at = now
                elif action is not None:
                    if action.action == "restore":
                        row.dismissed, row.snoozed_until = False, None
                    elif action.action == "dismiss":
                        row.dismissed, row.snoozed_until = True, None
                    else:
                        row.dismissed, row.snoozed_until, row.read_at = (
                            False,
                            now + action.minutes * 60,
                            None,
                        )
                else:
                    row.recommendation_until = now + 86400
            db.commit()
        return self.feed(account_id)
