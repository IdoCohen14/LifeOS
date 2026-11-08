from datetime import datetime, timezone

from lifeos.account_briefings import AccountBriefings
from lifeos.account_notices import AccountNotices
from lifeos.account_preferences import AccountPreferences
from lifeos.account_records import AccountRecords
from lifeos.accounts import AccountService


def test_owned_scheduled_briefings_are_opt_in_idempotent_and_private(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    a = auth.register("brief-a", "fixture password a")
    b = auth.register("brief-b", "fixture password b")
    service = AccountBriefings(engine)
    prefs = AccountPreferences(engine)
    now = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
    assert service.generate_due(a, now=now) == 0
    for owner in (a, b):
        prefs.put(owner, "briefings", {"daily_enabled": True, "weekly_enabled": True}, 0)
    AccountRecords(engine).save(a, "tasks", {"title": "Private", "due": "2026-11-02"})
    assert service.generate_due(a, now=now) == 2
    assert service.generate_due(a, now=now) == 0
    assert service.candidates(b, now=now) == []
    assert service.generate_due(b, now=now) == 2
    left = service.candidates(a, now=now)
    right = service.candidates(b, now=now)
    assert all(row["briefing"]["deadlines"] == 0 for row in right)
    assert (
        next(row for row in left if row["kind"] == "weekly_briefing")["briefing"]["deadlines"] == 1
    )
    assert {row["id"] for row in left} == {row["id"] for row in right}
    prefs.put(a, "briefings", {"daily_enabled": False, "weekly_enabled": False}, 1)
    assert service.candidates(a, now=now) == []
    assert len(service.candidates(b, now=now)) == 2
    # Disabling briefings must not disable ordinary task notices; those depend on today.
    assert not any(
        row["kind"] in ("daily_briefing", "weekly_briefing")
        for row in AccountNotices(engine).feed(a)["items"]
    )
