from test_assistant_preferences import ask, configured, preferences


def test_saved_daily_limit_legacy_omission_and_explicit_clear(client):
    value = client.get("/planning/preferences").json()
    response = client.put("/planning/preferences", json={**value, "daily_limit_minutes": 120})
    assert response.status_code == 200
    saved = response.json()
    assert saved["daily_limit_minutes"] == 120
    legacy = {key: value for key, value in saved.items() if key != "daily_limit_minutes"}
    preserved = client.put("/planning/preferences", json=legacy).json()
    assert preserved["daily_limit_minutes"] == 120
    cleared = client.put(
        "/planning/preferences", json={**preserved, "daily_limit_minutes": None}
    ).json()
    assert cleared["daily_limit_minutes"] is None


def test_assistant_daily_cap_uses_explicit_opt_in_and_rechecks_before_save(
    client, setup_app, monkeypatch
):
    preferences(client, duration=30, daily_limit_minutes=120)
    configured(setup_app, monkeypatch, duration=30)
    for start, end in [("21:00", "22:00"), ("21:30", "22:30")]:
        assert (
            client.post(
                "/events",
                json={
                    "title": "Saved cap fixture",
                    "start": f"2026-10-28T{start}:00+02:00",
                    "end": f"2026-10-28T{end}:00+02:00",
                },
            ).status_code
            == 201
        )
    response = ask(client, "Find time tomorrow for 30 minutes")
    assert response.status_code == 200
    proposal = response.json()["proposal"]
    assert proposal["preference_source"]["daily_limit_minutes"] == 120
    assert (
        client.post(
            "/events",
            json={
                "title": "Extra cap fixture",
                "start": "2026-10-28T23:00:00+02:00",
                "end": "2026-10-28T23:15:00+02:00",
            },
        ).status_code
        == 201
    )
    assert client.post("/assistant/confirm", json={"id": proposal["id"]}).status_code == 409
    blocked = ask(client, "Find time tomorrow for 30 minutes").json()
    assert blocked["proposal"] is None
    preferences(client, assistant_enabled=False, daily_limit_minutes=120)
    assert ask(client, "Find time tomorrow for 30 minutes").json()["proposal"] is not None
