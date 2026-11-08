from datetime import datetime


def clock(monkeypatch, value="2026-10-26T10:00:00+00:00"):
    from lifeos import task_planning

    monkeypatch.setattr(task_planning, "current_time", lambda: datetime.fromisoformat(value))


def request(task, **changes):
    return {
        "task_id": task["id"],
        "day": "2026-10-27",
        "days": 1,
        "duration": 30,
        "window_start": "08:00",
        "window_end": "20:00",
        **changes,
    }


def test_maximum_date_only_deadline_stays_date_only_when_planned(client, monkeypatch):
    clock(monkeypatch)
    task = client.post(
        "/tasks", json={"title": "Maximum deadline fixture", "due": "9999-12-31"}
    ).json()
    result = client.post("/planning/propose", json=request(task))
    assert result.status_code == 200
    proposal = result.json()["proposal"]
    assert client.get("/events").json() == []
    saved = client.post("/assistant/confirm", json={"id": proposal["id"]})
    assert saved.status_code == 200
    assert client.post("/assistant/confirm", json={"id": proposal["id"]}).json() == saved.json()
    assert client.get("/tasks").json() == [task]
    assert task["due"] == "9999-12-31"


def test_task_planning_proposes_without_inference_and_commits_event_once(
    client, setup_app, monkeypatch
):
    import pytest

    clock(monkeypatch)
    monkeypatch.setattr(
        setup_app[0].state.assistant, "infer", lambda _: pytest.fail("Planner cannot infer")
    )
    task = client.post("/tasks", json={"title": "Call fixture", "due": "2026-10-28"}).json()
    client.post(
        "/events",
        json={
            "title": "Busy fixture",
            "start": "2026-10-27T06:00:00Z",
            "end": "2026-10-27T07:00:00Z",
        },
    )
    result = client.post("/planning/propose", json=request(task))
    assert result.status_code == 200
    proposal = result.json()["proposal"]
    assert proposal["payload"]["start"] == "2026-10-27T07:00:00Z"
    assert len(client.get("/events").json()) == 1
    saved = client.post("/assistant/confirm", json={"id": proposal["id"]})
    assert saved.status_code == 200
    assert client.post("/assistant/confirm", json={"id": proposal["id"]}).json() == saved.json()
    assert len(client.get("/events").json()) == 2
    existing = client.post("/planning/propose", json=request(task)).json()
    assert existing["proposal"] is None and existing["existing"]["id"] == saved.json()["id"]
    assert client.get("/tasks").json() == [task]


def test_task_planning_deadline_date_only_overdue_and_all_day_semantics(client, monkeypatch):
    clock(monkeypatch)
    task = client.post(
        "/tasks", json={"title": "Due fixture", "due": "2026-10-27T06:20:00Z"}
    ).json()
    assert client.post("/planning/propose", json=request(task)).json()["reason"] == "no_slot"
    allowed = client.post("/planning/propose", json=request(task, allow_after_due=True)).json()
    assert allowed["proposal"] and allowed["deadline_ignored"]
    client.put(f"/tasks/{task['id']}", json={"title": task["title"], "due": "2026-10-25"})
    assert client.post("/planning/propose", json=request(task)).json()["overdue"]
    client.post(
        "/events",
        json={
            "title": "All day fixture",
            "start": "2026-10-27",
            "end": "2026-10-28",
            "all_day": True,
        },
    )
    assert client.post("/planning/propose", json=request(task)).json()["reason"] == "no_slot"
    proposal = client.post("/planning/propose", json=request(task, days=2)).json()["proposal"]
    assert proposal["payload"]["start"] == "2026-10-28T06:00:00Z"
    client.put(f"/tasks/{task['id']}", json={"title": task["title"], "due": "2026-10-28"})
    assert client.post("/planning/propose", json=request(task, days=2)).json()["proposal"]


def test_task_planning_rejects_changed_source_zone_conflicts_and_past_start(client, monkeypatch):
    clock(monkeypatch)
    task = client.post("/tasks", json={"title": "Source fixture"}).json()

    def propose():
        return client.post("/planning/propose", json=request(task)).json()["proposal"]

    first = propose()
    client.put(f"/tasks/{task['id']}", json={"title": "Changed fixture"})
    assert client.post("/assistant/confirm", json={"id": first["id"]}).status_code == 409
    second = propose()
    client.put("/settings", json={"timezone": "UTC"})
    assert client.post("/assistant/confirm", json={"id": second["id"]}).status_code == 409
    client.put("/settings", json={"timezone": "Asia/Jerusalem"})
    third = propose()
    client.post(
        "/events",
        json={
            "title": "New conflict",
            "start": third["payload"]["start"],
            "end": third["payload"]["end"],
        },
    )
    assert client.post("/assistant/confirm", json={"id": third["id"]}).status_code == 409
    fourth = propose()
    clock(monkeypatch, "2026-10-27T22:00:00+00:00")
    assert client.post("/assistant/confirm", json={"id": fourth["id"]}).status_code == 409
    assert len(client.get("/events").json()) == 1


def test_task_planning_cancel_session_csrf_validation_and_link_cascades(client, monkeypatch):
    clock(monkeypatch)
    task = client.post("/tasks", json={"title": "Cascade fixture"}).json()
    for changes in [{"duration": 0}, {"days": 8}, {"window_start": "21:00"}, {"day": "2026-10-25"}]:
        assert client.post("/planning/propose", json=request(task, **changes)).status_code == 422
    proposal = client.post("/planning/propose", json=request(task)).json()["proposal"]
    assert client.delete(f"/planning/proposals/{proposal['id']}").status_code == 204
    assert client.post("/assistant/confirm", json={"id": proposal["id"]}).status_code == 404
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.post("/planning/propose", json=request(task)).status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    proposal = client.post("/planning/propose", json=request(task)).json()["proposal"]
    saved = client.post("/assistant/confirm", json={"id": proposal["id"]}).json()
    client.delete(f"/events/{saved['id']}")
    another = client.post("/planning/propose", json=request(task)).json()["proposal"]
    client.post("/assistant/confirm", json={"id": another["id"]})
    client.delete(f"/tasks/{task['id']}")
    assert len(client.get("/events").json()) == 1


def test_task_planning_parallel_proposals_cannot_double_book_one_task(
    client, setup_app, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor

    from fastapi import HTTPException
    from lifeos.security import token_hash

    clock(monkeypatch)
    task = client.post("/tasks", json={"title": "Parallel fixture"}).json()
    ids = [
        client.post("/planning/propose", json=request(task)).json()["proposal"]["id"]
        for _ in range(2)
    ]
    session_hash = token_hash(client.cookies.get("lifeos_session"))

    def confirm(id):
        try:
            setup_app[0].state.assistant.confirm(id, session_hash)
            return 200
        except HTTPException as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(confirm, ids)) == [200, 409]
    assert len(client.get("/events").json()) == 1


def test_planning_preferred_weekdays_filters_without_extending_range(client, monkeypatch):
    clock(monkeypatch)
    task = client.post("/tasks", json={"title": "Weekday fixture"}).json()
    # Tuesday27Oct excluded, Wednesday28Oct included, search still exactly2days.
    response = client.post("/planning/propose", json=request(task, days=2, weekdays=[3]))
    assert response.status_code == 200, response.text
    plan = response.json()["proposal"]
    assert plan["payload"]["start"] == "2026-10-28T06:00:00Z"
    assert client.get("/events").json() == []
    assert client.post("/assistant/confirm", json={"id": plan["id"]}).status_code == 200
    another = client.post("/tasks", json={"title": "Excluded fixture"}).json()
    empty = client.post("/planning/propose", json=request(another, days=2, weekdays=[4]))
    assert empty.status_code == 200 and empty.json()["reason"] == "no_slot"
    assert client.post("/planning/propose", json=request(another, weekdays=[])).status_code == 422


def test_planning_excluded_dst_boundary_is_not_resolved(client, monkeypatch):
    clock(monkeypatch, "2026-10-24T06:00:00+00:00")
    task = client.post("/tasks", json={"title": "DST weekday fixture"}).json()
    response = client.post(
        "/planning/propose",
        json=request(
            task, day="2026-10-25", days=2, weekdays=[1], window_start="01:30", window_end="02:30"
        ),
    )
    assert response.status_code == 200, response.text
    assert response.json()["proposal"]["payload"]["start"] == "2026-10-25T23:30:00Z"


def test_legacy_task_plan_without_weekdays_keeps_its_reviewed_date(client, setup_app, monkeypatch):
    import json

    from lifeos.assistant_models import AssistantProposal
    from sqlalchemy.orm import Session

    clock(monkeypatch)
    task = client.post("/tasks", json={"title": "Legacy weekday fixture"}).json()
    plan = client.post("/planning/propose", json=request(task)).json()["proposal"]
    with Session(setup_app[0].state.assistant.engine) as db:
        row = db.get(AssistantProposal, plan["id"])
        stored = json.loads(row.payload)
        stored["planning_task"]["request"].pop("weekdays")
        row.payload = json.dumps(stored)
        db.commit()
    value = client.get("/planning/preferences").json()
    assert (
        client.put(
            "/planning/preferences", json={**value, "enabled": True, "weekdays": [1]}
        ).status_code
        == 200
    )
    assert client.post("/assistant/confirm", json={"id": plan["id"]}).status_code == 200
    assert client.get("/events").json()[0]["start"] == plan["payload"]["start"]
