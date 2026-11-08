from test_web_push_transport import subscription


def configured(client):
    result = client.put("/push/config", json={"contact": "fixture@example.test", "revision": 0})
    assert result.status_code == 200
    return result.json()


def test_push_default_off_config_consent_and_encrypted_device_lifecycle(client, setup_app):
    initial = client.get("/push/config").json()
    assert initial == {"configured": False, "public_key": None, "contact": "", "revision": 0}
    cfg = configured(client)
    assert len(cfg["public_key"]) == 87 and "private" not in str(cfg)
    assert (
        client.put(
            "/push/config", json={"contact": "other@example.test", "revision": 0}
        ).status_code
        == 409
    )
    value = subscription()
    response = client.post("/push/subscriptions", json=value)
    assert response.status_code == 200
    device = response.json()
    assert device["enabled"] and value["endpoint"] not in response.text
    assert (
        client.post("/push/lookup", json={"endpoint": value["endpoint"]}).json()["id"]
        == device["id"]
    )
    assert client.get("/push/subscriptions/" + device["id"]).json()["enabled"]
    assert client.delete("/push/subscriptions/" + device["id"]).status_code == 204
    assert client.get("/push/subscriptions/" + device["id"]).status_code == 404


def test_push_auth_csrf_invalid_contact_and_unconfigured_registration(client):
    assert client.post("/push/subscriptions", json=subscription()).status_code == 409
    assert (
        client.put("/push/config", json={"contact": "bad contact", "revision": 0}).status_code
        == 422
    )
    token = client.headers.pop("X-CSRF-Token")
    assert (
        client.put(
            "/push/config", json={"contact": "fixture@example.test", "revision": 0}
        ).status_code
        == 403
    )
    client.headers["X-CSRF-Token"] = token
    client.cookies.clear()
    assert client.get("/push/config").status_code == 401


def test_push_delivery_dedup_quiet_retry_and_gone_device(client, setup_app, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from lifeos import web_push_delivery

    configured(client)
    device = client.post("/push/subscriptions", json=subscription()).json()
    now = datetime(2026, 10, 27, 10, tzinfo=timezone.utc)
    monkeypatch.setattr(web_push_delivery, "current_time", lambda: now)
    state = {
        "quiet": False,
        "stale_sources": [],
        "items": [{"id": "a" * 64, "read": False, "snoozed_until": None}],
    }
    called = []

    def sender(value, key, contact, payload):
        called.append(payload)
        return 201, 300

    runner = web_push_delivery.PushDeliveryService(
        setup_app[0].state.assistant.engine, setup_app[1], feed=lambda: state, sender=sender
    )
    assert runner.run_due() == 1
    assert set(called[0]) == {
        "id",
        "language",
        "zone",
        "quiet_enabled",
        "quiet_start",
        "quiet_end",
        "expires",
        "notice_title",
        "notice_body",
    }
    assert called[0]["notice_title"]
    now += timedelta(minutes=16)
    assert runner.run_due() == 0
    state["items"][0]["id"] = "b" * 64
    state["quiet"] = True
    assert runner.run_due() == 0
    state["quiet"] = False
    runner.sender = lambda *args: (503, 300)
    assert runner.run_due() == 1
    assert runner.run_due() == 0
    now += timedelta(minutes=6)
    runner.sender = lambda *args: (410, 300)
    assert runner.run_due() == 1
    assert client.get("/push/subscriptions/" + device["id"]).status_code == 404


def test_push_restore_scrubs_all_subscription_and_signing_state(client, setup_app):
    import sqlite3

    from lifeos.recovery import create_backup, unpack_backup

    configured(client)
    value = subscription()
    client.post("/push/subscriptions", json=value)
    backup = create_backup(setup_app[1], "push backup fixture password")
    entries, _ = unpack_backup(
        setup_app[1] / "backups" / (backup["id"] + ".lifeosbackup"), "push backup fixture password"
    )
    target = setup_app[1] / "inspected-push.sqlite3"
    target.write_bytes(entries["lifeos.sqlite3"])
    with sqlite3.connect(target) as db:
        for table in ["push_devices", "push_deliveries", "push_config"]:
            assert db.execute("SELECT count(*) FROM " + table).fetchone()[0] == 0
    from lifeos.recovery import restore_backup

    restored = setup_app[1] / "restored-push-fixture"
    restore_backup(
        setup_app[1] / "backups" / (backup["id"] + ".lifeosbackup"),
        "push backup fixture password",
        restored,
    )
    with sqlite3.connect(restored / "lifeos.sqlite3") as db:
        for table in ["push_devices", "push_deliveries", "push_config"]:
            assert db.execute("SELECT count(*) FROM " + table).fetchone()[0] == 0


def test_real_push_feed_handles_personal_events_and_rejects_completed_source_before_claim(
    client, setup_app, monkeypatch
):
    from datetime import datetime, timedelta, timezone

    from lifeos import web_push_delivery

    configured(client)
    device = client.post("/push/subscriptions", json=subscription()).json()
    now = datetime.now(timezone.utc)
    client.post(
        "/events",
        json={
            "title": "Current event fixture",
            "start": (now + timedelta(hours=1)).isoformat(),
            "end": (now + timedelta(hours=2)).isoformat(),
        },
    )
    task = client.post(
        "/tasks", json={"title": "Current deadline fixture", "due": now.date().isoformat()}
    ).json()
    feed = web_push_delivery.cached_feed(setup_app[0].state.assistant.engine)
    item = next(item for item in feed["items"] if task["id"] in item.get("source_ids", []))
    client.put("/tasks/" + task["id"], json={**task, "completed": True})
    runner = web_push_delivery.PushDeliveryService(
        setup_app[0].state.assistant.engine, setup_app[1], sender=lambda *args: (201, 300)
    )
    assert runner.claim(device["id"], item) is None


def test_push_attempt_limit_expiration_and_test_mode_never_sends(client, setup_app, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from lifeos import web_push_delivery
    from lifeos.credential_vault import CredentialVault
    from lifeos.web_push_models import PushDevice
    from sqlalchemy.orm import Session

    configured(client)
    device = client.post("/push/subscriptions", json=subscription()).json()
    now = datetime(2026, 10, 27, 10, tzinfo=timezone.utc)
    monkeypatch.setattr(web_push_delivery, "current_time", lambda: now)
    state = {"quiet": False, "stale_sources": [], "items": [{"id": "c" * 64, "read": False}]}
    attempts = []
    runner = web_push_delivery.PushDeliveryService(
        setup_app[0].state.assistant.engine,
        setup_app[1],
        feed=lambda: state,
        sender=lambda *args: attempts.append(True) or (503, 300),
    )
    for i in range(4):
        runner.run_due()
        now += timedelta(minutes=6)
    assert len(attempts) == 3
    with Session(runner.engine) as db:
        row = db.get(PushDevice, device["id"])
        value = CredentialVault(setup_app[1]).decrypt(row.subscription)
        value["expirationTime"] = 0
        row.subscription = CredentialVault(setup_app[1]).encrypt(value)
        db.commit()
    state["items"][0]["id"] = "d" * 64
    assert runner.run_due() == 0
    assert client.get("/push/subscriptions/" + device["id"]).status_code == 404
    monkeypatch.setenv("LIFEOS_TEST_MODE", "1")
    from pytest import fail

    monkeypatch.setattr(
        web_push_delivery, "send_push", lambda *args: fail("Test-mode default sender must not run")
    )
    assert web_push_delivery.PushDeliveryService(runner.engine, setup_app[1]).run_due() == 0


def test_push_elapsed_feed_budget_never_starts_transport(client, setup_app, monkeypatch):
    from types import SimpleNamespace

    import pytest
    from fastapi import HTTPException
    from lifeos import web_push_delivery

    configured(client)
    client.post("/push/subscriptions", json=subscription())
    clock = [0]
    monkeypatch.setattr(web_push_delivery, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    def delayed_feed():
        clock[0] = 21
        return {"quiet": False, "stale_sources": [], "items": [{"id": "e" * 64, "read": False}]}

    calls = []
    runner = web_push_delivery.PushDeliveryService(
        setup_app[0].state.assistant.engine,
        setup_app[1],
        feed=delayed_feed,
        sender=lambda *args: calls.append(True) or (201, 300),
    )
    with pytest.raises(HTTPException) as error:
        runner.run_due()
    assert error.value.status_code == 503 and not calls


def test_real_push_claim_rechecks_read_category_and_quiet(client, setup_app):
    from datetime import datetime, timezone

    from lifeos import web_push_delivery

    configured(client)
    device = client.post("/push/subscriptions", json=subscription()).json()
    task = client.post(
        "/tasks",
        json={"title": "Fresh push fixture", "due": datetime.now(timezone.utc).date().isoformat()},
    )
    task = task.json()
    client.put("/notifications/preferences", json={"quiet_enabled": False})
    runner = web_push_delivery.PushDeliveryService(
        setup_app[0].state.assistant.engine, setup_app[1], sender=lambda *args: (201, 300)
    )
    item = web_push_delivery.cached_feed(runner.engine)["items"][0]
    assert client.post("/notifications/read", json={"ids": [item["id"]]}).status_code == 200
    assert runner.claim(device["id"], item) is None
    client.put("/tasks/" + task["id"], json={**task, "title": "Unread guard fixture"})
    item = web_push_delivery.cached_feed(runner.engine)["items"][0]
    assert not item["read"]
    client.put(
        "/notifications/preferences",
        json={"quiet_enabled": True, "quiet_start": "00:00", "quiet_end": "00:00"},
    )
    assert runner.claim(device["id"], item) is None
    client.put("/notifications/preferences", json={"quiet_enabled": False, "tasks": False})
    assert runner.claim(device["id"], item) is None


def test_push_filtered_batches_do_not_starve_after_read_or_sent_prefix(client, setup_app):
    from datetime import datetime, timezone
    from uuid import uuid4

    from lifeos.models import Task
    from lifeos.notification_models import NotificationRead
    from lifeos.web_push_delivery import cached_feed, delivery_key
    from lifeos.web_push_models import PushDelivery
    from sqlalchemy import insert
    from sqlalchemy.orm import Session

    configured(client)
    device = client.post("/push/subscriptions", json=subscription()).json()
    engine = setup_app[0].state.assistant.engine
    today = datetime.now(timezone.utc).date().isoformat()
    with Session(engine) as db:
        db.execute(
            insert(Task),
            [
                {
                    "id": str(uuid4()),
                    "title": f"Batch fixture {i}",
                    "notes": "",
                    "priority": "high",
                    "due": today,
                    "completed": False,
                    "created_at": today,
                }
                for i in range(505)
            ],
        )
        db.commit()
    candidates, _ = setup_app[0].state.recommendations.candidates()
    with Session(engine) as db:
        db.execute(
            insert(NotificationRead),
            [{"id": item["id"], "read_at": 0} for item in candidates[:500]],
        )
        db.commit()
    feed = cached_feed(engine)
    assert len(feed["items"]) == 5
    with Session(engine) as db:
        for item in feed["items"][:4]:
            db.add(
                PushDelivery(
                    id=delivery_key((device["id"], 1), item),
                    device_id=device["id"],
                    created_at=0,
                    attempts=1,
                    next_attempt=0,
                    sent=True,
                )
            )
        db.commit()
    remaining = cached_feed(engine, device=(device["id"], 1))["items"]
    assert [item["id"] for item in remaining] == [feed["items"][4]["id"]]


def test_push_worker_runtime_guard_without_transport_creation(client, setup_app, monkeypatch):
    import http.client
    import importlib.util
    from pathlib import Path

    import pytest
    from lifeos.data_lock import data_lock

    path = Path(__file__).resolve().parents[1] / "services/worker/worker.py"
    spec = importlib.util.spec_from_file_location("push_fixture_worker", path)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    called = []

    class Service:
        def __init__(self, engine, directory):
            pass

        def run_due(self):
            with pytest.raises(RuntimeError):
                with data_lock(setup_app[1]):
                    pytest.fail("Push callback must hold runtime guard")
            called.append(True)

    monkeypatch.setattr(
        http.client,
        "HTTPSConnection",
        lambda *args, **kwargs: pytest.fail("No default-off Push transport construction"),
    )
    monkeypatch.setattr(worker, "PushDeliveryService", Service)
    worker.deliver_push()
    assert called == [True]


def test_push_device_cap_and_snoozed_source_stays_inapp_only(client, setup_app):
    from datetime import datetime, timezone

    from lifeos import web_push_delivery

    configured(client)
    devices = []
    for i in range(5):
        response = client.post(
            "/push/subscriptions",
            json=subscription(f"https://fcm.googleapis.com/fcm/send/cap-fixture-token-{i}"),
        )
        assert response.status_code == 200
        devices.append(response.json())
    assert (
        client.post(
            "/push/subscriptions",
            json=subscription("https://fcm.googleapis.com/fcm/send/cap-fixture-token-extra"),
        ).status_code
        == 429
    )
    assert len(client.get("/push/subscriptions").json()) == 5
    client.post(
        "/tasks",
        json={
            "title": "Snoozed Push fixture",
            "due": datetime.now(timezone.utc).date().isoformat(),
        },
    )
    client.put("/notifications/preferences", json={"quiet_enabled": False})
    runner = web_push_delivery.PushDeliveryService(
        setup_app[0].state.assistant.engine, setup_app[1], sender=lambda *args: (201, 300)
    )
    item = web_push_delivery.cached_feed(runner.engine)["items"][0]
    assert (
        client.post(
            "/notifications/action", json={"id": item["id"], "action": "snooze", "minutes": 15}
        ).status_code
        == 200
    )
    assert runner.claim(devices[0]["id"], item) is None
