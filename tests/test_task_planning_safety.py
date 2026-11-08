from datetime import datetime, timedelta

from test_task_planning import clock, request


def test_task_planning_rounds_custom_window_to_real_quarter_hours(client, monkeypatch):
    clock(monkeypatch)
    task = client.post("/tasks", json={"title": "Grid fixture"}).json()
    proposal = client.post("/planning/propose", json=request(task, window_start="08:07")).json()[
        "proposal"
    ]
    assert proposal["payload"]["start"] == "2026-10-27T06:15:00Z"


def test_task_planning_final_clock_check_rejects_start_that_passes_during_scan(client, monkeypatch):
    from lifeos import task_planning

    clock(monkeypatch)
    task = client.post("/tasks", json={"title": "Final clock fixture"}).json()
    proposal = client.post("/planning/propose", json=request(task)).json()["proposal"]
    original = task_planning.cached_calendar

    def delayed(*args):
        events = original(*args)
        start = datetime.fromisoformat(proposal["payload"]["start"].replace("Z", "+00:00"))
        monkeypatch.setattr(task_planning, "current_time", lambda: start + timedelta(seconds=1))
        return events

    monkeypatch.setattr(task_planning, "cached_calendar", delayed)
    assert client.post("/assistant/confirm", json={"id": proposal["id"]}).status_code == 409
    assert client.get("/events").json() == []


def test_task_planning_dst_endpoints_assignment_markers_and_resource_refusal(client, monkeypatch):
    import time
    from zoneinfo import ZoneInfo

    from lifeos import task_planning

    clock(monkeypatch, "2026-10-24T10:00:00+00:00")
    task = client.post("/tasks", json={"title": "DST planning fixture", "due": "2026-10-25"}).json()
    assert (
        client.post(
            "/planning/propose",
            json=request(task, day="2026-10-25", window_start="01:30", window_end="04:00"),
        ).status_code
        == 422
    )
    body = task_planning.PlanningInput(**request(task, day="2026-10-25"))
    now = datetime.fromisoformat("2026-10-24T10:00:00+00:00")
    slot, _ = task_planning.choose_slot(
        body,
        None,
        [
            {
                "source": "assignment",
                "start": "2026-10-25T06:00:00Z",
                "end": "2026-10-25T06:01:00Z",
                "all_day": False,
            }
        ],
        now,
        ZoneInfo("Asia/Jerusalem"),
        time.monotonic() + 10,
    )
    assert slot[0].isoformat() == "2026-10-25T06:00:00+00:00"
    monkeypatch.setattr(task_planning, "MAX_SECONDS", 0)
    assert client.post("/planning/propose", json=request(task, day="2026-10-25")).status_code == 503
    assert client.get("/events").json() == []


def test_task_planning_past_block_can_be_replanned_without_deleting_history(client, monkeypatch):
    clock(monkeypatch)
    task = client.post("/tasks", json={"title": "Replan fixture"}).json()
    first = client.post("/planning/propose", json=request(task)).json()["proposal"]
    assert client.post("/assistant/confirm", json={"id": first["id"]}).status_code == 200
    clock(monkeypatch, "2026-10-28T05:00:00+00:00")
    second = client.post("/planning/propose", json=request(task, day="2026-10-28")).json()[
        "proposal"
    ]
    assert client.post("/assistant/confirm", json={"id": second["id"]}).status_code == 200
    assert len(client.get("/events").json()) == 2
    assert not client.get("/tasks").json()[0]["completed"]


def test_task_planning_active_proposals_are_bounded_and_cancellation_frees_capacity(
    client, monkeypatch
):
    clock(monkeypatch)
    task = client.post("/tasks", json={"title": "Proposal capacity fixture"}).json()
    proposals = [
        client.post("/planning/propose", json=request(task)).json()["proposal"] for _ in range(20)
    ]
    assert client.post("/planning/propose", json=request(task)).status_code == 429
    assert client.delete(f"/planning/proposals/{proposals[0]['id']}").status_code == 204
    assert client.post("/planning/propose", json=request(task)).status_code == 200
    assert client.get("/events").json() == []


def test_task_planning_final_expiry_check_rolls_back_the_claim_and_event(client, monkeypatch):
    import time
    from types import SimpleNamespace

    from lifeos import task_planning

    clock(monkeypatch)
    task = client.post("/tasks", json={"title": "Final expiry fixture"}).json()
    proposal = client.post("/planning/propose", json=request(task)).json()["proposal"]
    now = time.time()
    monkeypatch.setattr(
        task_planning, "time", SimpleNamespace(time=lambda: now + 1000, monotonic=time.monotonic)
    )
    assert client.post("/assistant/confirm", json={"id": proposal["id"]}).status_code == 404
    assert client.get("/events").json() == []
