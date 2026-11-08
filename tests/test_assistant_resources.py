import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from lifeos.assistant_models import AssistantProposal
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def mocked(client, setup_app, monkeypatch, action="find_slot"):
    from lifeos import assistant

    clock = [datetime(2026, 10, 27, 6, tzinfo=timezone.utc)]
    monkeypatch.setattr(assistant, "current_time", lambda: clock[0], raising=False)
    setup_app[0].state.assistant.http = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "message": {
                        "content": json.dumps(
                            {
                                "action": action,
                                "title": "Resource fixture",
                                "date": "2026-10-28",
                                "duration": 60,
                            }
                        )
                    }
                },
            )
        )
    )
    return clock


def ask(client):
    return client.post("/assistant/chat", json={"message": "Find 60 minutes free on 2026-10-28"})


@pytest.mark.parametrize("action", ["schedule", "find_slot"])
def test_assistant_rejects_calendar_resource_exhaustion_without_partial_result(
    client, setup_app, monkeypatch, action
):
    from lifeos import briefings

    mocked(client, setup_app, monkeypatch, action)
    client.post(
        "/events",
        json={
            "title": "Busy fixture",
            "start": "2026-10-28T08:00:00+02:00",
            "end": "2026-10-28T09:00:00+02:00",
        },
    )
    monkeypatch.setattr(briefings, "MAX_EVENTS", 0)
    response = ask(client)
    assert response.status_code == 503 and response.json() == {"detail": "assistant_resource_limit"}
    with Session(setup_app[0].state.assistant.engine) as db:
        assert db.scalar(select(func.count()).select_from(AssistantProposal)) == 0


def test_assistant_last_busy_slot_scan_cannot_publish_after_deadline(
    client, setup_app, monkeypatch
):
    import builtins
    import time
    from types import SimpleNamespace

    from lifeos import assistant, briefings

    mocked(client, setup_app, monkeypatch)
    client.post(
        "/events",
        json={
            "title": "Busy all-day fixture",
            "start": "2026-10-28",
            "end": "2026-10-29",
            "all_day": True,
        },
    )
    ticks = [0]
    clock = SimpleNamespace(time=time.time, monotonic=lambda: ticks[0])
    monkeypatch.setattr(assistant, "time", clock)
    monkeypatch.setattr(briefings, "time", clock)
    scans = [0]

    def slow_last_scan(values):
        result = builtins.any(values)
        scans[0] += 1
        if scans[0] == 45:
            ticks[0] = 20
        return result

    monkeypatch.setattr(assistant, "any", slow_last_scan, raising=False)
    response = ask(client)
    assert scans[0] == 45
    assert response.status_code == 503 and response.json() == {"detail": "assistant_resource_limit"}
    with Session(setup_app[0].state.assistant.engine) as db:
        assert db.scalar(select(func.count()).select_from(AssistantProposal)) == 0


def test_assistant_schedule_task_scan_limit_is_explicit(client, setup_app, monkeypatch):
    from lifeos import assistant

    mocked(client, setup_app, monkeypatch, "schedule")
    for index in range(2):
        client.post("/tasks", json={"title": f"Task fixture {index}", "due": "2026-10-28"})
    monkeypatch.setattr(assistant, "MAX_TASKS", 1, raising=False)
    assert ask(client).status_code == 503


@pytest.mark.parametrize("changed", ["past", "zone"])
def test_assistant_free_slot_rejects_past_or_different_zone(
    client, setup_app, monkeypatch, changed
):
    clock = mocked(client, setup_app, monkeypatch)
    proposal = ask(client).json()["proposal"]
    if changed == "past":
        clock[0] = datetime.fromisoformat(
            proposal["payload"]["start"].replace("Z", "+00:00")
        ) + timedelta(seconds=1)
    else:
        client.put("/settings", json={"timezone": "America/New_York"})
    assert client.post("/assistant/confirm", json={"id": proposal["id"]}).status_code == 409
    assert client.get("/events").json() == []


@pytest.mark.parametrize(
    "action,failure",
    [("find_slot", value) for value in ("budget", "session", "proposal", "past")]
    + [("task", value) for value in ("budget", "session", "proposal")],
)
def test_assistant_postinsert_failure_rolls_back_source_and_claim(
    client, setup_app, monkeypatch, action, failure
):
    import time

    from fastapi import HTTPException
    from lifeos import assistant
    from lifeos.assistant_models import AssistantProposal
    from lifeos.models import LoginSession
    from sqlalchemy import event, update
    from sqlalchemy.orm import Session

    clock = mocked(client, setup_app, monkeypatch, action)
    proposal = ask(client).json()["proposal"]
    table = "tasks" if action == "task" else "events"
    engine = setup_app[0].state.assistant.engine
    flushed = []
    original = assistant.check_budget

    def checked(*args, **kwargs):
        if flushed and failure == "budget":
            raise HTTPException(503, "assistant_resource_limit")
        original(*args, **kwargs)

    monkeypatch.setattr(assistant, "check_budget", checked)

    def changed(connection, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO " + table):
            flushed.append(True)
            if failure == "past":
                clock[0] = datetime.fromisoformat(
                    proposal["payload"]["start"].replace("Z", "+00:00")
                ) + timedelta(seconds=1)
            elif failure == "session":
                connection.execute(update(LoginSession).values(expires=0))
            elif failure == "proposal":
                connection.execute(
                    update(AssistantProposal)
                    .where(AssistantProposal.id == proposal["id"])
                    .values(expires=0)
                )

    event.listen(engine, "after_cursor_execute", changed)
    try:
        response = client.post("/assistant/confirm", json={"id": proposal["id"]})
    finally:
        event.remove(engine, "after_cursor_execute", changed)
    assert (
        flushed
        and response.status_code
        == {"budget": 503, "session": 401, "proposal": 404, "past": 409}[failure]
    )
    assert client.get("/" + table).json() == []
    with Session(engine) as db:
        row = db.get(AssistantProposal, proposal["id"])
        assert row.confirmed_id is None and row.expires > time.time()
    clock[0] = datetime(2026, 10, 27, 6, tzinfo=timezone.utc)
    monkeypatch.setattr(assistant, "check_budget", original)
    assert client.post("/assistant/confirm", json={"id": proposal["id"]}).status_code == 200
    assert len(client.get("/" + table).json()) == 1


def test_assistant_schedule_projects_task_fields_and_preserves_all_day_dates(
    client, setup_app, monkeypatch
):
    from sqlalchemy import event

    mocked(client, setup_app, monkeypatch, "schedule")
    client.post(
        "/tasks",
        json={
            "title": "Dated task fixture",
            "due": "2026-10-28",
            "notes": "Sensitive fixture note",
        },
    )
    client.post(
        "/events",
        json={
            "title": "All-day fixture",
            "start": "2026-10-28",
            "end": "2026-10-29",
            "all_day": True,
        },
    )
    queries = []

    def observed(connection, cursor, statement, parameters, context, many):
        if statement.startswith("SELECT") and (
            "FROM tasks" in statement or "FROM events" in statement
        ):
            queries.append(statement)

    engine = setup_app[0].state.assistant.engine
    event.listen(engine, "before_cursor_execute", observed)
    try:
        response = ask(client)
    finally:
        event.remove(engine, "before_cursor_execute", observed)
    assert response.status_code == 200
    schedule = response.json()["schedule"]
    assert schedule["tasks"] == [{"title": "Dated task fixture", "due": "2026-10-28"}]
    assert schedule["events"][0]["start"] == "2026-10-28"
    assert all("tasks.notes" not in query and "events.notes" not in query for query in queries)


def test_assistant_confirmation_calendar_limit_and_legacy_zone_require_fresh_review(
    client, setup_app, monkeypatch
):
    from lifeos import briefings
    from lifeos.assistant_models import AssistantProposal
    from sqlalchemy.orm import Session

    mocked(client, setup_app, monkeypatch)
    proposal = ask(client).json()["proposal"]
    client.post(
        "/events",
        json={
            "title": "Unrelated fixture",
            "start": "2026-10-28T21:00:00+02:00",
            "end": "2026-10-28T22:00:00+02:00",
        },
    )
    monkeypatch.setattr(briefings, "MAX_EVENTS", 0)
    assert client.post("/assistant/confirm", json={"id": proposal["id"]}).status_code == 503
    monkeypatch.setattr(briefings, "MAX_EVENTS", 20000)
    with Session(setup_app[0].state.assistant.engine) as db:
        row = db.get(AssistantProposal, proposal["id"])
        assert row.confirmed_id is None
        payload = json.loads(row.payload)
        payload.pop("free_slot_timezone")
        row.payload = json.dumps(payload)
        db.commit()
    assert client.post("/assistant/confirm", json={"id": proposal["id"]}).status_code == 409
    assert len(client.get("/events").json()) == 1


def test_assistant_operational_deadline_excludes_mock_inference_but_checks_task_fetch(
    client, setup_app, monkeypatch
):
    import time
    from types import SimpleNamespace

    from lifeos import assistant, briefings
    from sqlalchemy import event

    mocked(client, setup_app, monkeypatch, "schedule")
    ticks = [0]
    real_time = time.time
    monkeypatch.setattr(
        assistant, "time", SimpleNamespace(time=real_time, monotonic=lambda: ticks[0])
    )
    monkeypatch.setattr(
        briefings, "time", SimpleNamespace(time=real_time, monotonic=lambda: ticks[0])
    )
    original = setup_app[0].state.assistant.infer

    def delayed(payload):
        ticks[0] += 100
        return original(payload)

    monkeypatch.setattr(setup_app[0].state.assistant, "infer", delayed)
    client.post("/tasks", json={"title": "Budget fetch fixture", "due": "2026-10-28"})
    assert ask(client).status_code == 200

    def exceeded(connection, cursor, statement, parameters, context, many):
        if statement.startswith("SELECT") and "FROM tasks" in statement:
            ticks[0] += 20

    engine = setup_app[0].state.assistant.engine
    event.listen(engine, "after_cursor_execute", exceeded)
    try:
        response = ask(client)
    finally:
        event.remove(engine, "after_cursor_execute", exceeded)
    assert response.status_code == 503 and response.json() == {"detail": "assistant_resource_limit"}
