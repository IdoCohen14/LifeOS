from datetime import datetime, timezone


def clock(monkeypatch, instant="2026-10-26T10:00:00+00:00"):
    from lifeos import briefings, notifications, recommendations

    now = datetime.fromisoformat(instant)
    for module in [briefings, notifications, recommendations]:
        monkeypatch.setattr(module, "current_time", lambda: now)
    return now


def test_briefing_schedule_defaults_validation_and_request_guards(client, monkeypatch):
    clock(monkeypatch)
    schedule = client.get("/briefings/schedule").json()
    assert not schedule["daily_enabled"] and not schedule["weekly_enabled"]
    assert schedule["daily_time"] == "08:00" and schedule["weekly_day"] == 6
    for body in [
        {"daily_time": "25:00"},
        {"weekly_day": 7},
        {"extra": True},
        {"daily_enabled": True, "daily_time": "01:30"},
        {"daily_enabled": True, "daily_time": "02:30"},
    ]:
        assert client.put("/briefings/schedule", json=body).status_code == 422
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.put("/briefings/schedule", json={"daily_enabled": True}).status_code == 403
    assert client.post("/briefings/check").status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    assert client.post("/briefings/check").json()["generated"] == 0


def test_scheduled_daily_weekly_snapshots_are_deduped_and_notification_actions_apply(
    client, setup_app, monkeypatch
):
    clock(monkeypatch)
    task = client.post(
        "/tasks", json={"title": "Briefing source fixture", "due": "2026-10-26"}
    ).json()
    assert (
        client.put(
            "/briefings/schedule", json={"daily_enabled": True, "weekly_enabled": True}
        ).status_code
        == 200
    )
    assert client.post("/briefings/check").json()["generated"] == 2
    assert client.post("/briefings/check").json()["generated"] == 0
    cards = [
        item
        for item in client.get("/notifications").json()["items"]
        if item["kind"].endswith("_briefing")
    ]
    assert len(cards) == 2 and all(item["briefing"]["deadlines"] == 1 for item in cards)
    assert all("Briefing source fixture" not in str(item["briefing"]) for item in cards)
    id = cards[0]["id"]
    assert client.post("/notifications/read", json={"ids": [id]}).status_code == 200
    assert (
        client.post(
            "/notifications/action", json={"id": id, "action": "snooze", "minutes": 15}
        ).status_code
        == 200
    )
    assert (
        len(client.put("/notifications/preferences", json={"briefings": False}).json()["items"])
        == 1
    )
    assert client.get("/tasks").json() == [task]
    from lifeos.briefings import BriefingService

    assert BriefingService(setup_app[0].state.recommendations.engine).generate_due() == 0


def test_briefing_due_boundaries_current_period_catchup_and_no_backfill(client, monkeypatch):
    clock(monkeypatch, "2026-10-26T05:59:59+00:00")
    client.put(
        "/briefings/schedule", json={"daily_enabled": True, "weekly_enabled": True, "weekly_day": 1}
    )
    assert client.post("/briefings/check").json()["generated"] == 0
    clock(monkeypatch, "2026-10-26T06:00:00+00:00")
    assert client.post("/briefings/check").json()["generated"] == 1
    clock(monkeypatch, "2026-10-27T07:00:00+00:00")
    assert client.post("/briefings/check").json()["generated"] == 2
    clock(monkeypatch, "2026-11-12T10:00:00+00:00")
    assert client.post("/briefings/check").json()["generated"] == 2
    assert (
        len(
            [
                item
                for item in client.get("/notifications").json()["items"]
                if item["kind"].endswith("_briefing")
            ]
        )
        == 2
    )


def test_briefing_facts_overlap_date_only_dst_and_assignment_identity():
    from lifeos.briefings import summarize

    now = datetime(2026, 10, 25, 10, tzinfo=timezone.utc)
    event = {
        "id": "same",
        "source": "personal",
        "start": "2026-10-24T21:00:00Z",
        "end": "2026-10-25T22:00:00Z",
        "all_day": False,
    }
    events = [
        event,
        event,
        {**event, "source": "google"},
        {"id": "all", "start": "2026-10-25", "end": "2026-10-26", "all_day": True},
        {**event, "id": "marker", "source": "assignment"},
    ]
    tasks = [
        ("2026-10-25", False),
        ("2026-10-25T09:00:00Z", False),
        (None, False),
        ("2026-10-25", True),
    ]
    result = summarize(tasks, events, now, "Asia/Jerusalem", 1)
    assert result["minutes"] == 1500 and result["events"] == 3 and result["all_day"] == 1
    assert result["deadlines"] == 1 and result["overdue"] == 1 and result["undated"] == 1


def test_briefing_resource_failure_and_changed_config_publish_no_partial_snapshot(
    client, setup_app, monkeypatch
):
    from lifeos import briefings

    clock(monkeypatch)
    client.put("/briefings/schedule", json={"daily_enabled": True})
    client.post(
        "/events",
        json={
            "title": "Limit fixture",
            "start": "2026-10-26",
            "end": "2026-10-27",
            "all_day": True,
        },
    )
    monkeypatch.setattr(briefings, "MAX_EVENTS", 0)
    assert client.post("/briefings/check").json()["generated"] == 0
    assert client.get("/briefings/schedule").json()["last_error"] == "briefing_resource_limit"
    assert client.get("/notifications").status_code == 503
    monkeypatch.setattr(briefings, "MAX_EVENTS", 20000)
    assert not any(
        item["kind"].endswith("_briefing") for item in client.get("/notifications").json()["items"]
    )
    original = briefings.summarize

    def change(*args, **kwargs):
        result = original(*args, **kwargs)
        client.put("/briefings/schedule", json={"daily_enabled": False})
        return result

    monkeypatch.setattr(briefings, "summarize", change)
    assert client.post("/briefings/check").json()["generated"] == 0


def test_briefing_parallel_checks_publish_one_snapshot(client, setup_app, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from lifeos import briefings

    clock(monkeypatch)
    client.put("/briefings/schedule", json={"daily_enabled": True})
    barrier = Barrier(2)
    original = briefings.summarize

    def synchronized(*args, **kwargs):
        barrier.wait(timeout=5)
        return original(*args, **kwargs)

    monkeypatch.setattr(briefings, "summarize", synchronized)
    service = briefings.BriefingService(setup_app[0].state.recommendations.engine)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.generate_due(), range(2)))
    assert sorted(results) == [0, 1]


def test_briefing_worker_uses_runtime_guard_without_network_or_inference(
    client, setup_app, monkeypatch
):
    import importlib.util
    from pathlib import Path

    import httpx
    import pytest
    from lifeos.data_lock import data_lock

    path = Path(__file__).resolve().parents[1] / "services/worker/worker.py"
    spec = importlib.util.spec_from_file_location("briefing_fixture_worker", path)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    called = []

    class Service:
        def __init__(self, engine):
            pass

        def generate_due(self):
            with pytest.raises(RuntimeError):
                with data_lock(setup_app[1]):
                    pytest.fail("Briefing callback must hold runtime guard")
            called.append(True)

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda *args, **kwargs: pytest.fail("No network client for briefing generation"),
    )
    monkeypatch.setattr(worker, "BriefingService", Service)
    worker.generate_briefings()
    assert called == [True]


def test_briefing_budget_stops_during_academic_expansion(client, monkeypatch):
    from lifeos import academic_calendar, briefings

    clock(monkeypatch)
    term = client.post(
        "/academic/terms",
        json={"name": "Budget term", "start_date": "2026-10-01", "end_date": "2027-02-01"},
    ).json()
    course = client.post(
        "/academic/courses", json={"name": "Budget course", "term_id": term["id"]}
    ).json()
    assert (
        client.post(
            "/academic/timetable",
            json={
                "course_id": course["id"],
                "weekday": 0,
                "start_time": "10:00",
                "end_time": "11:00",
                "timezone": "Asia/Jerusalem",
            },
        ).status_code
        == 201
    )
    client.put("/briefings/schedule", json={"daily_enabled": True})
    original = academic_calendar.local_utc
    calls = []

    def counted(*args):
        calls.append(True)
        return original(*args)

    monkeypatch.setattr(academic_calendar, "local_utc", counted)
    monkeypatch.setattr(briefings, "MAX_EVENTS", 1)
    assert client.post("/briefings/check").json()["generated"] == 0
    assert len(calls) <= 4
    assert client.get("/briefings/schedule").json()["last_error"] == "briefing_resource_limit"


def test_briefing_write_time_expiry_rolls_back_every_staged_period(client, setup_app, monkeypatch):
    from types import SimpleNamespace

    from lifeos import briefings
    from sqlalchemy import event, text

    clock(monkeypatch)
    client.put("/briefings/schedule", json={"daily_enabled": True, "weekly_enabled": True})
    tick = [0]
    monkeypatch.setattr(briefings, "time", SimpleNamespace(monotonic=lambda: tick[0]))
    engine = setup_app[0].state.recommendations.engine

    def slow(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO scheduled_briefings"):
            tick[0] = 11

    event.listen(engine, "after_cursor_execute", slow)
    try:
        assert client.post("/briefings/check").json()["generated"] == 0
    finally:
        event.remove(engine, "after_cursor_execute", slow)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM scheduled_briefings")) == 0
    assert client.get("/briefings/schedule").json()["last_error"] == "briefing_resource_limit"


def test_scheduled_briefing_uses_selected_cached_providers_and_captures_staleness(
    client, setup_app, monkeypatch
):
    import json

    from lifeos.google_models import GoogleCalendar, GoogleConnection, GoogleRecord
    from lifeos.moodle_models import MoodleConnection, MoodleEvent
    from sqlalchemy.orm import Session

    clock(monkeypatch)
    engine = setup_app[0].state.recommendations.engine
    with Session(engine) as db:
        db.add_all(
            [
                GoogleConnection(id=1, state="connected", last_success=1),
                MoodleConnection(id=1, state="error", last_success=1, error="fixture"),
            ]
        )
        db.add_all(
            [
                GoogleCalendar(
                    id="selected", name="Fixture selected", timezone="UTC", selected=True
                ),
                GoogleCalendar(
                    id="excluded", name="Fixture excluded", timezone="UTC", selected=False
                ),
            ]
        )
        db.flush()
        for calendar in ["selected", "excluded"]:
            payload = {
                "id": calendar,
                "source": "google",
                "title": "Cached fixture",
                "start": "2026-10-26T11:00:00Z",
                "end": "2026-10-26T12:00:00Z",
                "all_day": False,
            }
            db.add(
                GoogleRecord(
                    calendar_id=calendar,
                    external_id="event",
                    kind="visible",
                    payload=json.dumps(payload),
                )
            )
        db.add(
            MoodleEvent(
                id="moodle",
                payload=json.dumps(
                    {
                        "id": "moodle",
                        "source": "moodle",
                        "title": "Cached day fixture",
                        "start": "2026-10-26",
                        "end": "2026-10-27",
                        "all_day": True,
                    }
                ),
            )
        )
        db.commit()
    client.put("/briefings/schedule", json={"daily_enabled": True})
    assert client.post("/briefings/check").json()["generated"] == 1
    summary = next(
        item["briefing"]
        for item in client.get("/notifications").json()["items"]
        if item["kind"] == "daily_briefing"
    )
    assert summary["events"] == 2 and summary["minutes"] == 60 and summary["all_day"] == 1
    assert summary["stale_sources"] == ["Google Calendar", "Moodle"]
