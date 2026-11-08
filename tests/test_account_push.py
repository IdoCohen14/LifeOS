import pytest
from fastapi import HTTPException
from lifeos.accounts import AccountService
from lifeos.web_push import ConfigInput, WebPushService
from lifeos.web_push_transport import SubscriptionInput
from test_web_push_transport import subscription


def test_real_account_candidate_reaches_mock_push_with_course_and_deadline(client, setup_app):
    from datetime import datetime, timedelta, timezone

    from lifeos.account_academic import AccountAcademic
    from lifeos.account_preferences import AccountPreferences
    from lifeos.web_push_delivery import PushDeliveryService

    engine = setup_app[0].state.assistant.engine
    owner = AccountService(engine, enabled=True).register("course-delivery", "fixture password")
    service = WebPushService(engine, setup_app[1], account_id=owner)
    service.configure(ConfigInput(contact="fixture@example.test", revision=0))
    service.register(SubscriptionInput.model_validate(subscription()))
    AccountPreferences(engine).put(owner, "notifications", {"quiet_enabled": False}, 0)
    now = datetime.now(timezone.utc)
    academic = AccountAcademic(engine)
    term = academic.save_root(owner, "terms", {
        "name": "Fixture term", "start_date": now.date().isoformat(),
        "end_date": (now + timedelta(days=60)).date().isoformat(),
    })
    course = academic.save_root(owner, "courses", {"name": "מערכות הפעלה", "term_id": term["id"]})
    academic.save_child(owner, "items", {
        "title": "מטלה 1", "course_id": course["id"],
        "due": (now + timedelta(hours=24)).isoformat(), "kind": "assignment",
    })
    sent = []
    worker = PushDeliveryService(
        engine, setup_app[1], account_id=owner,
        sender=lambda sub, key, contact, payload: sent.append(payload) or (201, 0),
    )
    assert worker.run_due() == 1
    assert sent[0]["notice_title"] == "מועד הגשה מתקרב"
    assert "מטלה 1 · מערכות הפעלה" in sent[0]["notice_body"]
    assert "24 שעות" in sent[0]["notice_body"]
    assert worker.run_due() == 0


def test_owned_push_keys_and_devices_are_private_even_for_same_endpoint(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    a = auth.register("push-a", "fixture password a")
    b = auth.register("push-b", "fixture password b")
    left = WebPushService(engine, setup_app[1], account_id=a)
    right = WebPushService(engine, setup_app[1], account_id=b)
    assert not left.config()["configured"]
    ca = left.configure(ConfigInput(contact="fixture@example.test", revision=0))
    cb = right.configure(ConfigInput(contact="fixture@example.test", revision=0))
    assert ca["public_key"] != cb["public_key"]
    value = SubscriptionInput.model_validate(subscription())
    da = left.register(value)
    assert right.lookup(value.endpoint) is None
    db = right.register(value)
    assert da["id"] != db["id"]
    with pytest.raises(HTTPException):
        right.status(da["id"])
    right.remove(da["id"])
    assert left.status(da["id"])["enabled"]
    left.remove(da["id"])
    assert left.devices() == [] and len(right.devices()) == 1
    assert client.get("/push/subscriptions").json() == []


def test_owned_delivery_reads_only_owner_feed_and_receipts(client, setup_app):
    from datetime import datetime, timezone

    from lifeos.account_preferences import AccountPreferences
    from lifeos.account_records import AccountRecords
    from lifeos.web_push_delivery import PushDeliveryService

    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    owners = [auth.register("deliver-" + name, "fixture password " + name) for name in ("a", "b")]
    devices = []
    for index, owner in enumerate(owners):
        service = WebPushService(engine, setup_app[1], account_id=owner)
        service.configure(ConfigInput(contact=f"fixture{index}@example.test", revision=0))
        devices.append(service.register(SubscriptionInput.model_validate(subscription()))["id"])
        AccountPreferences(engine).put(owner, "notifications", {"quiet_enabled": False}, 0)
        AccountRecords(engine).save(
            owner,
            "tasks",
            {"title": f"Private {index}", "due": datetime.now(timezone.utc).date().isoformat()},
        )
    sent = []
    worker = PushDeliveryService(
        engine,
        setup_app[1],
        account_id=owners[0],
        sender=lambda sub, key, contact, payload: sent.append((contact, payload)) or (201, 0),
    )
    assert worker.run_due() == 1 and sent[0][0] == "fixture0@example.test"
    assert worker.run_due() == 0
    from lifeos.account_notices import AccountNotices

    item = AccountNotices(engine).feed(owners[0])["items"][0]
    assert worker.claim(devices[1], item) is None
    assert len(sent) == 1
    other = PushDeliveryService(
        engine,
        setup_app[1],
        account_id=owners[1],
        sender=lambda sub, key, contact, payload: sent.append((contact, payload)) or (201, 0),
    )
    assert other.run_due() == 1 and sent[1][0] == "fixture1@example.test"
