from test_task_planning import clock, request


def busy_fixture(client):
    for start, end in [("21:00", "22:00"), ("21:30", "22:30")]:
        assert (
            client.post(
                "/events",
                json={
                    "title": "Occupancy fixture",
                    "start": f"2026-10-27T{start}:00+02:00",
                    "end": f"2026-10-27T{end}:00+02:00",
                },
            ).status_code
            == 201
        )


def test_task_daily_cap_counts_union_outside_window_and_can_choose_next_day(client, monkeypatch):
    clock(monkeypatch)
    busy_fixture(client)
    task = client.post("/tasks", json={"title": "Daily cap fixture"}).json()
    allowed = client.post("/planning/propose", json=request(task, daily_limit_minutes=120))
    assert allowed.status_code == 200
    assert allowed.json()["proposal"] is not None
    blocked = client.post("/planning/propose", json=request(task, daily_limit_minutes=105))
    assert blocked.status_code == 200 and blocked.json()["proposal"] is None
    next_day = client.post(
        "/planning/propose", json=request(task, daily_limit_minutes=105, days=2)
    ).json()
    assert next_day["proposal"]["payload"]["start"].startswith("2026-10-28")


def test_task_daily_cap_is_rechecked_before_confirmation(client, monkeypatch):
    clock(monkeypatch)
    busy_fixture(client)
    task = client.post("/tasks", json={"title": "Recheck cap fixture"}).json()
    proposed = client.post("/planning/propose", json=request(task, daily_limit_minutes=120)).json()[
        "proposal"
    ]
    assert (
        client.post(
            "/events",
            json={
                "title": "Extra late fixture",
                "start": "2026-10-27T23:00:00+02:00",
                "end": "2026-10-27T23:15:00+02:00",
            },
        ).status_code
        == 201
    )
    response = client.post("/assistant/confirm", json={"id": proposed["id"]})
    assert response.status_code == 409
    assert len(client.get("/events").json()) == 3
