from lifeos.account_moodle_changes import AccountMoodleChanges
from lifeos.account_providers import AccountProviders
from lifeos.accounts import AccountService


def test_moodle_changes_are_atomic_owned_and_reset_on_reconnect(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    a = auth.register("changes-a", "fixture password a")
    b = auth.register("changes-b", "fixture password b")
    store = AccountProviders(engine, setup_app[1])
    changes = AccountMoodleChanges(engine)
    event = {
        "id": "shared",
        "title": "Deadline",
        "start": "2026-11-01",
        "end": "2026-11-02",
        "all_day": True,
        "source": "moodle",
        "created_at": "2026-10-30T00:00:00Z",
    }

    def sync(owner, records):
        lease = store.begin_sync(owner, "moodle")
        store.commit_sync(owner, "moodle", lease["owner"], lease["revision"], records)

    for owner in (a, b):
        store.configure(owner, "moodle", {"url": "fixture"})
        sync(owner, [event])
        assert changes.list(owner) == []
    sync(a, [{**event, "start": "2026-11-03", "end": "2026-11-04"}])
    first = changes.list(a)
    assert len(first) == 1 and first[0]["kind"] == "changed"
    assert first[0]["previous"]["start"] == "2026-11-01"
    assert changes.list(b) == []
    assert changes.candidates(a)[0]["previous_start"] == "2026-11-01"
    sync(a, [])
    assert {row["kind"] for row in changes.list(a)} == {"changed", "removed"}
    store.configure(a, "moodle", {"url": "another-fixture"})
    assert changes.list(a) == []
    sync(a, [event])
    assert changes.list(a) == []
