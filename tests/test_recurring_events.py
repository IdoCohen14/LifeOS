from datetime import datetime, timezone

import pytest


def body(**changes):
    return {
        "title": "Weekly fixture",
        "notes": "Fixture only",
        "day": "2026-10-20",
        "clock": "09:00",
        "duration": 60,
        "count": 3,
        "all_day": False,
        "timezone": "Asia/Jerusalem",
        **changes,
    }


def frozen(monkeypatch):
    from lifeos import recurring_events

    monkeypatch.setattr(
        recurring_events, "current_time", lambda: datetime(2026, 10, 19, 6, tzinfo=timezone.utc)
    )
    return recurring_events


def test_preview_no_events_then_atomic_weekly_save_and_retry_does_not_resurrect(
    client, monkeypatch
):
    frozen(monkeypatch)
    response = client.post("/recurrence/preview", json=body())
    assert response.status_code == 200
    preview = response.json()
    assert client.get("/events").json() == []
    rows = preview["events"]
    assert len(rows) == 3
    assert rows[0]["start"] == "2026-10-20T06:00:00Z"
    assert rows[1]["start"] == "2026-10-27T07:00:00Z"
    saved = client.post("/recurrence/confirm", json={"id": preview["id"]})
    assert saved.status_code == 200 and len(saved.json()["event_ids"]) == 3
    assert len(client.get("/events").json()) == 3
    first = saved.json()["event_ids"][0]
    client.delete("/events/" + first)
    assert client.post("/recurrence/confirm", json={"id": preview["id"]}).json() == saved.json()
    assert len(client.get("/events").json()) == 2
    assert client.get("/tasks").json() == []


def test_all_day_remains_date_only_and_dst_failure_rejects_entire_preview(client, monkeypatch):
    frozen(monkeypatch)
    result = client.post("/recurrence/preview", json=body(all_day=True)).json()
    assert result["events"][0]["start"] == "2026-10-20"
    assert result["events"][0]["end"] == "2026-10-21"
    assert (
        client.post("/recurrence/preview", json=body(day="2026-10-25", clock="01:30")).status_code
        == 422
    )
    assert client.get("/events").json() == []


def test_recurring_confirmation_zone_change_expiry_and_cancel_fences(client, monkeypatch):
    frozen(monkeypatch)
    preview = client.post("/recurrence/preview", json=body()).json()
    settings = client.get("/settings").json()
    client.put("/settings", json={**settings, "timezone": "UTC"})
    assert client.post("/recurrence/confirm", json={"id": preview["id"]}).status_code == 409
    client.put("/settings", json=settings)
    assert client.delete("/recurrence/proposals/" + preview["id"]).status_code == 204
    assert client.post("/recurrence/confirm", json={"id": preview["id"]}).status_code == 404
    assert client.get("/events").json() == []


@pytest.mark.parametrize(
    "changes",
    [
        {"count": 1},
        {"count": 53},
        {"duration": 7},
        {"duration": True},
        {"clock": "24:00"},
        {"day": "2026-10-01"},
        {"timezone": "UTC"},
        {"surprise": "value"},
    ],
)
def test_recurring_input_rejects_invalid_or_stale_values(client, monkeypatch, changes):
    frozen(monkeypatch)
    assert client.post("/recurrence/preview", json=body(**changes)).status_code in (409, 422)
    assert client.get("/events").json() == []


def test_recurring_confirmation_rolls_back_after_actual_event_flush(client, setup_app, monkeypatch):
    from fastapi import HTTPException
    from sqlalchemy import event

    module = frozen(monkeypatch)
    preview = client.post("/recurrence/preview", json=body()).json()
    flushed = []
    engine = setup_app[0].state.assistant.engine

    def observed(connection, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO events"):
            flushed.append(True)

    event.listen(engine, "after_cursor_execute", observed)
    original = module.budget

    def expired(deadline):
        if flushed:
            raise HTTPException(503, "recurrence_resource_limit")
        original(deadline)

    monkeypatch.setattr(module, "budget", expired)
    try:
        assert client.post("/recurrence/confirm", json={"id": preview["id"]}).status_code == 503
    finally:
        event.remove(engine, "after_cursor_execute", observed)
    assert flushed and client.get("/events").json() == []
    monkeypatch.setattr(module, "budget", original)
    assert client.post("/recurrence/confirm", json={"id": preview["id"]}).status_code == 200
    assert len(client.get("/events").json()) == 3


def test_recurring_owner_csrf_and_expired_preview(client, monkeypatch):
    from lifeos.recurring_events import RecurringProposal
    from sqlalchemy.orm import Session

    frozen(monkeypatch)
    preview = client.post("/recurrence/preview", json=body()).json()
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.post("/recurrence/confirm", json={"id": preview["id"]}).status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    login = client.post("/session", json={"password": "correct horse battery staple"})
    client.headers["X-CSRF-Token"] = login.json()["csrf"]
    assert client.post("/recurrence/confirm", json={"id": preview["id"]}).status_code == 404
    assert client.delete("/recurrence/proposals/" + preview["id"]).status_code == 404
    own = client.post("/recurrence/preview", json=body()).json()
    from lifeos.db import data_directory, open_database

    engine = open_database(data_directory())
    try:
        with Session(engine) as db:
            db.get(RecurringProposal, own["id"]).expires = 0
            db.commit()
    finally:
        engine.dispose()
    assert client.post("/recurrence/confirm", json={"id": own["id"]}).status_code == 404
    assert client.get("/events").json() == []
