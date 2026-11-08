import pytest

DEFAULTS = {
    "enabled": False,
    "assistant_enabled": False,
    "duration": 30,
    "daily_limit_minutes": None,
    "days": 1,
    "window_start": "08:00",
    "window_end": "20:00",
    "revision": 0,
    "weekdays": list(range(1, 8)),
}


def test_explicit_planning_preferences_defaults_save_reset_and_stale_writes(client):
    assert client.get("/planning/preferences").json() == DEFAULTS
    value = {
        **DEFAULTS,
        "enabled": True,
        "duration": 45,
        "days": 3,
        "window_start": "09:00",
        "window_end": "17:00",
    }
    response = client.put("/planning/preferences", json=value)
    assert response.status_code == 200
    saved = response.json()
    assert saved == {**value, "revision": 1}
    assert client.get("/planning/preferences").json() == saved
    assert client.put("/planning/preferences", json=value).status_code == 409
    assert (
        client.request("DELETE", "/planning/preferences", json={"revision": 0}).status_code == 409
    )
    reset = client.request("DELETE", "/planning/preferences", json={"revision": 1})
    assert reset.json() == {**DEFAULTS, "revision": 2}
    assert client.put("/planning/preferences", json=saved).status_code == 409
    assert client.get("/tasks").json() == [] and client.get("/events").json() == []


@pytest.mark.parametrize(
    "patch",
    [
        {"duration": 6},
        {"duration": True},
        {"duration": 245},
        {"duration": 30.0},
        {"days": 0},
        {"days": 8},
        {"enabled": "true"},
        {"revision": -1},
        {"window_start": "8:00"},
        {"window_end": "24:00"},
        {"window_end": "08:00"},
        {"window_start": "19:45"},
        {"surprise": "text"},
    ],
)
def test_planning_preferences_reject_invalid_values_without_writing(client, patch):
    result = client.put("/planning/preferences", json={**DEFAULTS, **patch})
    assert result.status_code == 422
    assert client.get("/planning/preferences").json() == DEFAULTS


def test_planning_preferences_require_auth_csrf_and_support_disabling_without_erasing(client):
    saved = client.put(
        "/planning/preferences", json={**DEFAULTS, "enabled": True, "duration": 60}
    ).json()
    off = client.put("/planning/preferences", json={**saved, "enabled": False}).json()
    assert off["duration"] == 60 and not off["enabled"]
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.put("/planning/preferences", json=off).status_code == 403
    assert (
        client.request(
            "DELETE", "/planning/preferences", json={"revision": off["revision"]}
        ).status_code
        == 403
    )
    client.headers["X-CSRF-Token"] = csrf
    client.cookies.clear()
    assert client.get("/planning/preferences").status_code == 401


@pytest.mark.parametrize(
    "weekdays", [None, [], [0], [8], [True], [1.0], ["1"], [1, 1], list(range(1, 9))]
)
def test_preferred_weekdays_reject_invalid_and_preserve_values(client, weekdays):
    before = client.get("/planning/preferences").json()
    assert (
        client.put("/planning/preferences", json={**before, "weekdays": weekdays}).status_code
        == 422
    )
    assert client.get("/planning/preferences").json() == before


def test_preferred_weekdays_save_legacy_update_and_reset(client):
    before = client.get("/planning/preferences").json()
    saved = client.put(
        "/planning/preferences", json={**before, "weekdays": [7, 1, 3], "enabled": True}
    ).json()
    assert saved["weekdays"] == [1, 3, 7]
    legacy = {key: value for key, value in saved.items() if key != "weekdays"}
    updated = client.put("/planning/preferences", json={**legacy, "duration": 45}).json()
    assert updated["weekdays"] == [1, 3, 7]
    reset = client.request(
        "DELETE", "/planning/preferences", json={"revision": updated["revision"]}
    ).json()
    assert (
        reset["weekdays"] == list(range(1, 8))
        and not reset["enabled"]
        and not reset["assistant_enabled"]
    )


def test_populated_weekday_migration_preserves_prior_defaults_and_optins(client, setup_app):
    from alembic import command
    from alembic.config import Config
    from lifeos.db import ROOT, migrate

    value = client.get("/planning/preferences").json()
    saved = client.put(
        "/planning/preferences",
        json={
            **value,
            "enabled": True,
            "assistant_enabled": True,
            "duration": 45,
            "weekdays": [1, 3],
        },
    ).json()
    engine = setup_app[0].state.assistant.engine
    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "services/api/alembic"))
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.downgrade(cfg, "0021")
    migrate(engine)
    restored = client.get("/planning/preferences").json()
    assert restored == {**saved, "weekdays": list(range(1, 8))}
