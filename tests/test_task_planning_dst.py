import json
from datetime import datetime, timezone

import pytest


def planned(client, monkeypatch, busy=False, later_busy=False, end="04:00"):
    from lifeos import task_planning

    monkeypatch.setattr(
        task_planning, "current_time", lambda: datetime(2026, 10, 24, 6, tzinfo=timezone.utc)
    )
    task = client.post("/tasks", json={"title": "Strict DST fixture"}).json()
    if busy:
        assert (
            client.post(
                "/events",
                json={
                    "title": "First busy fixture",
                    "start": "2026-10-25T00:00:00+03:00",
                    "end": "2026-10-25T01:00:00+03:00",
                },
            ).status_code
            == 201
        )
    if later_busy:
        assert (
            client.post(
                "/events",
                json={
                    "title": "Later busy fixture",
                    "start": "2026-10-25T02:00:00+02:00",
                    "end": "2026-10-25T03:00:00+02:00",
                },
            ).status_code
            == 201
        )
    response = client.post(
        "/planning/propose",
        json={
            "task_id": task["id"],
            "day": "2026-10-25",
            "days": 1,
            "duration": 60,
            "window_start": "00:00",
            "window_end": end,
        },
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize(
    "busy,later_busy,start",
    [
        (False, False, "2026-10-25T00:00:00Z"),
        (True, False, "2026-10-25T00:00:00Z"),
        (True, True, "2026-10-25T01:00:00Z"),
    ],
)
def test_task_planner_skips_ambiguous_endpoints_and_rechecks_later_conflicts(
    client, monkeypatch, busy, later_busy, start
):
    proposal = planned(client, monkeypatch, busy, later_busy)["proposal"]
    assert proposal["payload"]["start"] == start
    result = client.post("/assistant/confirm", json={"id": proposal["id"]})
    assert result.status_code == 200


def test_task_planner_reports_no_slot_when_only_ambiguous_endpoints_fit(client, monkeypatch):
    result = planned(client, monkeypatch, end="02:00")
    assert result["proposal"] is None and result["reason"] == "no_slot"
    assert client.get("/events").json() == []


def test_old_task_proposal_ambiguous_endpoints_cannot_be_approved(client, setup_app, monkeypatch):
    from lifeos.assistant_models import AssistantProposal
    from sqlalchemy.orm import Session

    proposal = planned(client, monkeypatch)["proposal"]
    engine = setup_app[0].state.assistant.engine
    with Session(engine) as db:
        row = db.get(AssistantProposal, proposal["id"])
        payload = json.loads(row.payload)
        payload["record"]["start"] = "2026-10-24T22:00:00Z"
        payload["record"]["end"] = "2026-10-24T23:00:00Z"
        row.payload = json.dumps(payload)
        db.commit()
    assert client.post("/assistant/confirm", json={"id": proposal["id"]}).status_code == 409
    assert client.get("/events").json() == []
    with Session(engine) as db:
        assert db.get(AssistantProposal, proposal["id"]).confirmed_id is None


def test_task_planner_does_not_round_a_blocked_window_to_datetime_overflow(client, monkeypatch):
    assert (
        client.post(
            "/events",
            json={
                "title": "Long busy fixture",
                "start": "2026-10-24T00:00:00Z",
                "end": "9999-12-31T23:59:59.999999Z",
            },
        ).status_code
        == 201
    )
    result = planned(client, monkeypatch)
    assert result["proposal"] is None and result["reason"] == "no_slot"
