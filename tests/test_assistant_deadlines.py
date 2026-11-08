import json
from datetime import datetime, timezone

import httpx
import pytest


def setup(client, setup_app, monkeypatch, action="find_slot"):
    from lifeos import assistant

    monkeypatch.setattr(
        assistant, "current_time", lambda: datetime(2026, 10, 27, 6, tzinfo=timezone.utc)
    )
    setup_app[0].state.assistant.http = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "message": {
                        "content": json.dumps(
                            {
                                "action": action,
                                "title": "Availability fixture",
                                "date": "2026-10-28",
                                "duration": 60,
                            }
                        )
                    }
                },
            )
        )
    )
    term = client.post(
        "/academic/terms",
        json={"name": "Term fixture", "start_date": "2026-10-01", "end_date": "2027-02-01"},
    ).json()
    return client.post(
        "/academic/courses", json={"name": "Course fixture", "term_id": term["id"]}
    ).json()


def ask(client):
    return client.post("/assistant/chat", json={"message": "Find 60 minutes free on 2026-10-28"})


@pytest.mark.parametrize("due", ["2026-10-28", "2026-10-28T06:00:00Z"])
def test_assistant_deadline_is_visible_but_not_busy(client, setup_app, monkeypatch, due):
    course = setup(client, setup_app, monkeypatch)
    item = client.post(
        "/academic/items",
        json={
            "course_id": course["id"],
            "title": "Deadline fixture",
            "kind": "assignment",
            "due": due,
        },
    ).json()
    response = ask(client)
    assert response.status_code == 200 and response.json()["proposal"] is not None
    proposal = response.json()["proposal"]
    assert proposal["payload"]["start"] == "2026-10-28T06:00:00Z"
    assert client.post("/assistant/confirm", json={"id": proposal["id"]}).status_code == 200
    assert client.get("/academic/items").json()[0] == item
    assert not client.get("/tasks").json()[0]["completed"]
    assert any(row["source"] == "assignment" for row in client.get("/academic/calendar").json())


@pytest.mark.parametrize("kind,status", [("assignment", 200), ("exam", 409), ("personal", 409)])
def test_assistant_approval_ignores_new_deadline_but_rejects_busy_event(
    client, setup_app, monkeypatch, kind, status
):
    course = setup(client, setup_app, monkeypatch)
    proposal = ask(client).json()["proposal"]
    if kind == "personal":
        assert (
            client.post(
                "/events",
                json={
                    "title": "Busy fixture",
                    "start": "2026-10-28",
                    "end": "2026-10-29",
                    "all_day": True,
                },
            ).status_code
            == 201
        )
    else:
        assert (
            client.post(
                "/academic/items",
                json={
                    "course_id": course["id"],
                    "title": "Later item fixture",
                    "kind": kind,
                    "due": "2026-10-28T06:00:00Z",
                    "duration_minutes": 60,
                },
            ).status_code
            == 201
        )
    assert client.post("/assistant/confirm", json={"id": proposal["id"]}).status_code == status
    if kind != "personal":
        assert client.get("/academic/items").json()[0]["kind"] == kind


def test_assistant_schedule_retains_deadlines_and_real_timetable_stays_busy(
    client, setup_app, monkeypatch
):
    course = setup(client, setup_app, monkeypatch, action="schedule")
    client.post(
        "/academic/items",
        json={
            "course_id": course["id"],
            "title": "Schedule deadline fixture",
            "kind": "assignment",
            "due": "2026-10-28",
        },
    )
    response = ask(client).json()["schedule"]
    assert any(row["source"] == "assignment" for row in response["events"])
    client.post(
        "/academic/timetable",
        json={
            "course_id": course["id"],
            "weekday": 3,
            "start_time": "08:00",
            "end_time": "09:00",
            "timezone": "Asia/Jerusalem",
        },
    )
    setup_app[0].state.assistant.http = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "message": {
                        "content": json.dumps(
                            {
                                "action": "find_slot",
                                "title": "Slot fixture",
                                "date": "2026-10-28",
                                "duration": 60,
                            }
                        )
                    }
                },
            )
        )
    )
    assert ask(client).json()["proposal"]["payload"]["start"] == "2026-10-28T07:00:00Z"
