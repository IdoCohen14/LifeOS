from datetime import datetime, timedelta, timezone

import pytest
from lifeos.account_preferences import AccountPreferences
from lifeos.proactive_planning import ProactivePlanning
from test_proactive_planning import state


def test_explicit_preferences_are_owned_versioned_and_archive_validated(client, setup_app):
    import json

    from lifeos.account_archive import AccountArchive
    from lifeos.account_restore import validate_tables

    engine, owner, other, _, _, _ = state(setup_app)
    prefs = AccountPreferences(engine)
    defaults = prefs.get(owner, "secretary")
    assert defaults["values"]["push_daily_limit"] == 0
    assert defaults["values"]["request_followup_minutes"] == 0
    prefs.put(owner, "secretary", {"reply_style": "standard", "push_daily_limit": 3}, 0)
    assert prefs.get(other, "secretary")["values"]["reply_style"] == "brief"
    with pytest.raises(ValueError):
        prefs.put(owner, "secretary", {"push_daily_limit": 6}, 0)
    with pytest.raises(ValueError):
        prefs.put(owner, "secretary", {"push_daily_limit": 99}, 1)
    tables = json.loads(AccountArchive(engine, setup_app[1]).export(owner))["tables"]
    validate_tables(owner, tables)
    row = next(row for row in tables["account_preferences"] if row["kind"] == "secretary")
    assert json.loads(row["payload"])["push_daily_limit"] == 3
    row["payload"] = '{"push_daily_limit":99}'
    with pytest.raises(ValueError):
        validate_tables(owner, tables)


def test_suggestion_snooze_survives_recalculation_and_new_deadline_can_surface(client, setup_app):
    from lifeos.account_records import AccountRecords

    engine, owner, _, _, task, now = state(setup_app)
    planner = ProactivePlanning(engine)
    candidate = planner.suggestion(owner, now=now)["suggestion"]
    planner.dismiss(owner, candidate["id"], now=now)
    assert planner.suggestion(owner, now=now + timedelta(minutes=20))["suggestion"] is None
    AccountRecords(engine).save(
        owner,
        "tasks",
        {"title": task["title"], "due": (now + timedelta(days=1)).date().isoformat()},
        task["id"],
    )
    assert planner.suggestion(owner, now=now + timedelta(minutes=20))["suggestion"] is not None
    prefs = AccountPreferences(engine)
    prefs.put(owner, "secretary", {"proactive_enabled": False}, 0)
    assert planner.suggestion(owner, now=now)["reason"] == "paused"


def test_daily_push_budget_is_per_device_and_resets_next_local_day(client, setup_app, monkeypatch):
    from lifeos.account_notices import AccountNotices
    from lifeos.account_records import AccountRecords
    from lifeos.accounts import AccountService
    from lifeos.web_push import ConfigInput, WebPushService
    from lifeos.web_push_delivery import PushDeliveryService
    from lifeos.web_push_models import AccountPushDevice
    from lifeos.web_push_transport import SubscriptionInput
    from sqlalchemy.orm import Session
    from test_web_push_transport import subscription

    engine = setup_app[0].state.assistant.engine
    owner = AccountService(engine, enabled=True).register("budget-fixture", "fixture password")
    prefs = AccountPreferences(engine)
    prefs.put(owner, "notifications", {"quiet_enabled": False}, 0)
    prefs.put(owner, "secretary", {"push_daily_limit": 3}, 0)
    push = WebPushService(engine, setup_app[1], account_id=owner)
    push.configure(ConfigInput(contact="fixture@example.test", revision=0))
    device = push.register(SubscriptionInput.model_validate(subscription()))["id"]
    for index in range(4):
        AccountRecords(engine).save(
            owner, "tasks", {"title": f"Budget fixture {index}", "due": "2000-01-01"}
        )
    worker = PushDeliveryService(engine, setup_app[1], account_id=owner)
    items = AccountNotices(engine).feed(owner)["items"]
    now = datetime.now(timezone.utc).replace(hour=20, minute=30, second=0, microsecond=0)
    monkeypatch.setattr("lifeos.web_push_delivery.current_time", lambda: now)
    for item in items[:3]:
        claim = worker.claim(device, item)
        assert claim is not None
        if item is items[0]:
            worker.outcome(device, claim[0], claim[1], 503, 300)
            now += timedelta(minutes=10)
            claim = worker.claim(device, item)
            assert claim is not None
        worker.outcome(device, claim[0], claim[1], 201, 0)
        with Session(engine) as db:
            db.get(AccountPushDevice, device).cooldown_until = 0
            db.commit()
    assert worker.claim(device, items[3]) is None
    second_device = push.register(
        SubscriptionInput.model_validate(
            subscription("https://fcm.googleapis.com/fcm/send/fixture-token-67890")
        )
    )["id"]
    assert worker.claim(second_device, items[3]) is not None
    now += timedelta(hours=3)
    assert worker.claim(device, items[3]) is not None


def test_default_followup_requires_explicit_preference_and_dedup_does_not_reset_it(
    client, setup_app
):
    import time

    from lifeos.account_notices import AccountNotices
    from lifeos.account_records import AccountRecords
    from lifeos.account_requests import AccountRequests

    engine, owner, _, _, _, _ = state(setup_app)
    task = AccountRecords(engine).save(
        owner, "tasks", {"title": "Explicit followup fixture", "due": "2000-01-01"}
    )
    notice = next(
        item
        for item in AccountNotices(engine).feed(owner)["items"]
        if task["id"] in item["source_ids"]
    )
    prefs = AccountPreferences(engine)
    prefs.put(owner, "secretary", {"request_followup_minutes": 60}, 0)
    requests = AccountRequests(engine)
    item = requests.create(owner, notice["id"])
    assert time.time() + 3500 < item["followup_at"] <= time.time() + 3601
    prefs.put(owner, "secretary", {"request_followup_minutes": 0}, 1)
    assert requests.create(owner, notice["id"])["followup_at"] == item["followup_at"]
