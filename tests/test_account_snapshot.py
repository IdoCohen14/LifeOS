from datetime import datetime, timezone

from lifeos.account_providers import AccountProviders
from lifeos.account_records import AccountRecords
from lifeos.account_snapshot import AccountSnapshot
from lifeos.accounts import AccountService


def test_owned_unified_calendar_and_briefing_ignore_other_and_legacy_records(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    a = auth.register("snapshot-a", "fixture password a")
    b = auth.register("snapshot-b", "fixture password b")
    store = AccountRecords(engine)
    task = store.save(a, "tasks", {"title": "Private task", "due": "2026-11-01"})
    event = {
        "title": "Private event",
        "start": "2026-11-01T08:00:00Z",
        "end": "2026-11-01T09:00:00Z",
    }
    personal = store.save(a, "events", event)
    store.save(b, "events", {**event, "title": "Other fixture"})
    assert client.post("/events", json={**event, "title": "Legacy fixture"}).status_code == 201
    providers = AccountProviders(engine, setup_app[1])
    providers.configure(a, "google", {"refresh_token": "synthetic"})
    lease = providers.begin_sync(a, "google")
    imported = {
        "id": "imported-fixture",
        "title": "Google fixture",
        "start": "2026-11-01T09:00:00Z",
        "end": "2026-11-01T10:00:00Z",
        "all_day": False,
        "source": "google",
        "created_at": "2026-10-30T00:00:00Z",
    }
    providers.commit_sync(
        a,
        "google",
        lease["owner"],
        lease["revision"],
        [{"id": "cache-fixture", "kind": "visible", "payload": imported}],
    )
    snapshot = AccountSnapshot(engine)
    result = snapshot.build(a)
    assert [row["id"] for row in result["tasks"]] == [task["id"]]
    assert {row["id"] for row in result["events"]} == {personal["id"], "imported-fixture"}
    summary = snapshot.briefing(a, 7, now=datetime(2026, 10, 30, tzinfo=timezone.utc))
    assert summary["events"] == 2 and summary["minutes"] == 120 and summary["deadlines"] == 1
    assert len(snapshot.build(b)["events"]) == 1
