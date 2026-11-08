import pytest
from lifeos.account_preferences import AccountPreferences
from lifeos.accounts import AccountService


def test_account_preferences_are_private_revisioned_and_reset_without_copying_legacy(
    client, setup_app
):
    engine = setup_app[0].state.assistant.engine
    accounts = AccountService(engine, enabled=True)
    a = accounts.register("prefs-a", "fixture password a")
    b = accounts.register("prefs-b", "fixture password b")
    store = AccountPreferences(engine)
    assert client.put("/settings", json={"display_name": "Legacy fixture"}).status_code == 200
    assert store.get(a, "settings")["values"]["display_name"] == ""
    saved = store.put(a, "settings", {"display_name": "Private fixture", "theme": "light"}, 0)
    assert saved["revision"] == 1
    assert store.get(b, "settings")["values"]["display_name"] == ""
    with pytest.raises(ValueError):
        store.put(a, "settings", {"theme": "dark"}, 0)
    reset = store.put(a, "settings", {}, 1, reset=True)
    assert reset["revision"] == 2 and reset["values"]["display_name"] == ""
    store.put(a, "history", {"enabled": True}, 0)
    assert store.get(b, "history")["values"]["enabled"] is False
    plan = store.put(
        a, "planning", {"enabled": True, "weekdays": [2, 4], "daily_limit_minutes": 120}, 0
    )
    assert plan["values"]["weekdays"] == [2, 4]
    assert store.get(b, "planning")["values"]["enabled"] is False
    assert client.get("/settings").json()["display_name"] == "Legacy fixture"


def test_owned_briefing_schedule_rejects_ambiguous_time_after_zone_change(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    owner = auth.register("briefing-zone", "fixture password")
    store = AccountPreferences(engine)
    store.put(owner, "settings", {"timezone": "UTC"}, 0)
    store.put(owner, "briefings", {"daily_enabled": True, "daily_time": "02:30"}, 0)
    with pytest.raises(ValueError):
        store.put(owner, "settings", {"timezone": "America/New_York"}, 1)
    assert store.get(owner, "settings")["values"]["timezone"] == "UTC"
