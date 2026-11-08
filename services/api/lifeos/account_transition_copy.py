"""Transform an offline staging database only; no filesystem/provider requests."""

import base64
import json
import time
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from .account_calendar import cache_id
from .account_preferences import SPECS


def rows(db, table):
    return [dict(row) for row in db.execute(f'SELECT * FROM "{table}"')]


def insert(db, table, values):
    # Table/column names come only from this module's fixed mapping, never a request.
    names = list(values)
    columns = ",".join('"' + name + '"' for name in names)
    db.execute(
        f'INSERT INTO "{table}" ({columns}) VALUES ({",".join("?" for _ in names)})',
        [values[name] for name in names],
    )


def preference(db, owner, kind, value, revision=1):
    insert(
        db,
        "account_preferences",
        {
            "account_id": owner,
            "kind": kind,
            "revision": revision,
            "payload": json.dumps(value, ensure_ascii=False),
        },
    )


def transform(db, plan, auth, vault):
    owner = plan["target_id"]
    now = datetime.now(timezone.utc).isoformat()
    insert(
        db,
        "accounts",
        {
            "id": owner,
            "login": plan["target_login"],
            "password_digest": json.dumps({"version": 1, **auth}),
            "created_at": now,
            "enabled": 1,
        },
    )
    for table in ("tasks", "events", "terms", "event_series"):
        db.execute(f'UPDATE "{table}" SET account_id=? WHERE account_id IS NULL', (owner,))
    for kind, table in (
        ("settings", "settings"),
        ("planning", "planning_preferences"),
        ("notifications", "notification_preferences"),
        ("history", "assistant_history_preferences"),
        ("briefings", "briefing_schedule"),
    ):
        schema, defaults = SPECS[kind]
        source = db.execute(f'SELECT * FROM "{table}" WHERE id=1').fetchone()
        values = {
            **defaults,
            **({key: source[key] for key in defaults if key in source.keys()} if source else {}),
        }
        if kind == "planning":
            if isinstance(values["weekdays"], str):
                values["weekdays"] = json.loads(values["weekdays"])
            values["revision"] = 0
        validated = schema.model_validate(values).model_dump(mode="json")
        validated.pop("revision", None)
        preference(db, owner, kind, validated)
    tracking = db.execute(
        "SELECT tracking_started_at FROM task_history_metadata WHERE id=1"
    ).fetchone()
    if tracking:
        preference(db, owner, "review_tracking", {"tracking_started_at": tracking[0]})
    for row in rows(db, "assistant_conversation_turns"):
        insert(
            db,
            "account_conversation_turns",
            {
                "id": str(uuid5(NAMESPACE_URL, owner + ":" + row["turn_id"])),
                "account_id": owner,
                "user_text": row["user_text"],
                "reply_text": row["assistant_text"],
                "created_at": row["created_at"],
                "include_context": 1,
            },
        )
    notices = {}
    for row in rows(db, "notification_reads"):
        notices.setdefault(row["id"], {})["read_at"] = row["read_at"]
    for row in rows(db, "notification_actions"):
        notices.setdefault(row["id"], {}).update(
            {key: row[key] for key in ("dismissed", "snoozed_until")}
        )
    for row in rows(db, "recommendation_dismissals"):
        notices.setdefault(row["id"], {})["recommendation_until"] = row["expires"]
    for id, values in notices.items():
        insert(
            db,
            "account_notice_states",
            {
                "account_id": owner,
                "id": id,
                "read_at": None,
                "dismissed": 0,
                "snoozed_until": None,
                "recommendation_until": None,
                "updated_at": int(time.time()),
                **values,
            },
        )
    for row in rows(db, "scheduled_briefings"):
        insert(db, "account_briefings", {"account_id": owner, **row})
    for row in rows(db, "moodle_changes"):
        insert(db, "account_moodle_changes", {"account_id": owner, **row})
    for provider in ("google", "gmail", "moodle"):
        connection = db.execute(f'SELECT * FROM "{provider}_connection" WHERE id=1').fetchone()
        if connection is None or connection["credentials"] is None:
            continue
        values = vault.decrypt(connection["credentials"])
        if provider == "google":
            values["selected_calendars"] = [
                row["id"] for row in rows(db, "google_calendars") if row["selected"]
            ]
        secret = vault.encrypt({"account_id": owner, "provider": provider, "values": values})
        insert(
            db,
            "account_providers",
            {
                "account_id": owner,
                "provider": provider,
                "credentials": secret,
                "revision": 1,
                "checkpoint": connection["history_id"] if provider == "gmail" else None,
                "lease_owner": None,
                "lease_until": 0,
                "last_success": connection["last_success"],
                "last_attempt": None,
                "error": connection["error"],
                "failures": connection["failures"],
                "next_sync": connection["next_sync"],
                "authorized": bool(
                    values.get("url") if provider == "moodle" else values.get("refresh_token")
                ),
            },
        )

        def cache(id, payload):
            insert(
                db,
                "account_provider_records",
                {
                    "account_id": owner,
                    "provider": provider,
                    "external_id": id,
                    "payload": json.dumps(payload, ensure_ascii=False),
                },
            )

        if provider == "google":
            for row in rows(db, "google_calendars"):
                cache(
                    cache_id("calendar", row["id"]),
                    {
                        "id": cache_id("calendar", row["id"]),
                        "kind": "calendar",
                        "calendar_id": row["id"],
                        "name": row["name"],
                        "timezone": row["timezone"],
                        "selected": bool(row["selected"]),
                        "token": row["sync_token"] if row["selected"] else None,
                    },
                )
            for row in rows(db, "google_records"):
                if row["calendar_id"] not in values["selected_calendars"]:
                    continue
                id = cache_id(row["kind"], row["calendar_id"], row["external_id"])
                cache(
                    id,
                    {
                        "id": id,
                        "kind": row["kind"],
                        "calendar_id": row["calendar_id"],
                        "external_id": row["external_id"],
                        "payload": json.loads(row["payload"]),
                    },
                )
        else:
            table = "gmail_messages" if provider == "gmail" else "moodle_events"
            for row in rows(db, table):
                cache(row["id"], json.loads(row["payload"]))
        if provider == "gmail":
            for row in rows(db, "gmail_reviewed"):
                insert(
                    db,
                    "account_mail_reviews",
                    {"account_id": owner, "provider_revision": 1, "message_id": row["id"]},
                )
        db.execute(
            f"UPDATE \"{provider}_connection\" SET credentials=NULL,lease_owner=NULL,lease_until=0,state='disconnected'"
        )
    config = db.execute("SELECT * FROM push_config WHERE id=1").fetchone()
    if config:
        insert(
            db,
            "account_push_config",
            {
                "id": owner,
                "public_key": config["public_key"],
                "private_key": vault.encrypt(
                    {"account_id": owner, "values": vault.decrypt(config["private_key"])}
                ),
                "contact": config["contact"],
                "revision": config["revision"],
            },
        )
        for row in rows(db, "push_devices"):
            insert(
                db,
                "account_push_devices",
                {
                    **row,
                    "account_id": owner,
                    "subscription": vault.encrypt(
                        {"account_id": owner, "values": vault.decrypt(row["subscription"])}
                    ),
                },
            )
        for row in rows(db, "push_deliveries"):
            insert(db, "account_push_deliveries", row)
    schedule = db.execute("SELECT * FROM backup_schedule WHERE id=1").fetchone()
    if schedule:
        encrypted = schedule["encrypted_password"]
        secret = None
        if encrypted:
            values = vault.decrypt(encrypted)
            secret = base64.b64encode(
                vault.encrypt({"account_id": owner, "password": values["password"]})
            ).decode()
        preference(
            db,
            owner,
            "backup_schedule",
            {
                "enabled": bool(schedule["enabled"]),
                "clock": schedule["clock"],
                "keep": schedule["keep"],
                "secret": secret,
                "last_attempt": schedule["last_attempt"],
                "last_success": schedule["last_success"],
                "last_day": schedule["last_day"],
                "last_zone": schedule["last_zone"],
                "last_error": schedule["last_error"],
                "files": [],
            },
            revision=schedule["revision"] + 1,
        )
    # Expired approvals and provider callback states never migrate into the new identity.
    for table in (
        "assistant_proposals",
        "course_batches",
        "recurrence_proposals",
        "series_delete_proposals",
        "series_reschedule_proposals",
        "google_oauth_states",
        "gmail_oauth_states",
    ):
        db.execute(f'DELETE FROM "{table}"')
    db.execute("DELETE FROM sessions WHERE expires<=?", (int(time.time()),))
    db.execute("UPDATE sessions SET account_id=?", (owner,))
