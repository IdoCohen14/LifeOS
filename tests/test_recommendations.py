from datetime import datetime, timezone


def test_recommendations_deadlines_hide_and_changes(client, setup_app, monkeypatch):
    from lifeos import recommendations

    monkeypatch.setattr(
        recommendations, "current_time", lambda: datetime(2026, 10, 26, 10, tzinfo=timezone.utc)
    )
    task = client.post(
        "/tasks", json={"title": "Urgent task", "due": "2026-10-25", "priority": "high"}
    ).json()
    client.post("/tasks", json={"title": "Done", "due": "2026-10-24", "completed": True})
    response = client.get("/recommendations").json()
    assert len(response["items"]) == 1
    item = response["items"][0]
    assert item["kind"] == "overdue" and item["title"] == "Urgent task"
    assert client.post("/recommendations/dismiss", json={"id": item["id"]}).json()["items"] == []
    assert client.post("/recommendations/dismiss", json={"id": item["id"]}).status_code == 200
    assert (
        next(t for t in client.get("/tasks").json() if t["id"] == task["id"])["completed"] is False
    )
    client.put(
        f"/tasks/{task['id']}",
        json={"title": "Changed task", "due": "2026-10-25", "priority": "high"},
    )
    changed = client.get("/recommendations").json()["items"]
    assert len(changed) == 1 and changed[0]["id"] != item["id"]
    client.headers["X-CSRF-Token"] = "bad"
    assert client.post("/recommendations/dismiss", json={"id": changed[0]["id"]}).status_code == 403


def test_recommendations_date_only_and_timed_deadlines(client, monkeypatch):
    from lifeos import recommendations

    monkeypatch.setattr(
        recommendations, "current_time", lambda: datetime(2026, 10, 26, 20, tzinfo=timezone.utc)
    )
    client.post("/tasks", json={"title": "Today date-only", "due": "2026-10-26"})
    client.post("/tasks", json={"title": "Timed overdue", "due": "2026-10-26T19:00:00Z"})
    kinds = {item["title"]: item["kind"] for item in client.get("/recommendations").json()["items"]}
    assert kinds == {"Today date-only": "due_soon", "Timed overdue": "overdue"}


def test_recommendations_conflicts_exclude_mirrors_and_adjacent_events(
    client, setup_app, monkeypatch
):
    from lifeos import recommendations

    monkeypatch.setattr(
        recommendations, "current_time", lambda: datetime(2026, 10, 26, 8, tzinfo=timezone.utc)
    )
    client.post(
        "/events",
        json={"title": "Meeting", "start": "2026-10-26T10:00:00Z", "end": "2026-10-26T11:00:00Z"},
    )
    client.post(
        "/events",
        json={"title": "Adjacent", "start": "2026-10-26T11:00:00Z", "end": "2026-10-26T12:00:00Z"},
    )
    monkeypatch.setattr(
        setup_app[0].state.google,
        "events",
        lambda: [
            {
                "id": "mirror",
                "title": "Meeting",
                "start": "2026-10-26T10:00:00Z",
                "end": "2026-10-26T11:00:00Z",
                "all_day": False,
                "source": "google",
            }
        ],
    )
    assert client.get("/recommendations").json()["items"] == []
    client.post(
        "/events",
        json={
            "title": "Overlapping",
            "start": "2026-10-26T10:30:00Z",
            "end": "2026-10-26T10:45:00Z",
        },
    )
    items = client.get("/recommendations").json()["items"]
    assert len(items) == 1 and items[0]["kind"] == "conflict"
    hidden_id = items[0]["id"]
    client.post("/recommendations/dismiss", json={"id": hidden_id})
    old = next(event for event in client.get("/events").json() if event["title"] == "Overlapping")
    client.delete(f"/events/{old['id']}")
    client.post(
        "/events",
        json={
            "title": "Overlapping",
            "start": "2026-10-26T10:30:00Z",
            "end": "2026-10-26T10:45:00Z",
        },
    )
    replacement = client.get("/recommendations").json()["items"]
    assert len(replacement) == 1 and replacement[0]["id"] != hidden_id


def test_recommendations_expire_without_inference_and_report_staleness(
    client, setup_app, monkeypatch
):
    from lifeos import recommendations

    monkeypatch.setattr(
        recommendations, "current_time", lambda: datetime(2026, 10, 26, 10, tzinfo=timezone.utc)
    )
    monkeypatch.setattr(
        setup_app[0].state.assistant,
        "infer",
        lambda _: (_ for _ in ()).throw(AssertionError("No automatic inference")),
    )
    monkeypatch.setattr(setup_app[0].state.google, "status", lambda: {"stale": True, "error": None})
    client.post("/tasks", json={"title": "Old task", "due": "2020-01-01"})
    feed = client.get("/recommendations").json()
    assert feed["stale_sources"] == ["Google Calendar"]
    id = feed["items"][0]["id"]
    client.post("/recommendations/dismiss", json={"id": id})
    assert not client.get("/recommendations").json()["items"]
    monkeypatch.setattr(
        recommendations, "current_time", lambda: datetime(2026, 10, 27, 11, tzinfo=timezone.utc)
    )
    assert client.get("/recommendations").json()["items"][0]["id"] == id


def test_recommendations_cap_visible_items(client, monkeypatch):
    from lifeos import recommendations

    monkeypatch.setattr(
        recommendations, "current_time", lambda: datetime(2026, 10, 26, 10, tzinfo=timezone.utc)
    )
    for index in range(7):
        client.post("/tasks", json={"title": f"Task {index}", "due": "2026-10-25"})
    feed = client.get("/recommendations").json()
    assert len(feed["items"]) == 5 and feed["truncated"]
    assert client.post("/recommendations/dismiss", json={"id": "0" * 64}).status_code == 404
