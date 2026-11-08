from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient


def clock(monkeypatch, value):
    from lifeos import notifications, recommendations

    instant = datetime.fromisoformat(value)
    monkeypatch.setattr(notifications, "current_time", lambda: instant)
    monkeypatch.setattr(recommendations, "current_time", lambda: instant)


def test_notifications_read_is_persistent_and_changed_versions_are_unread(
    client, setup_app, monkeypatch
):
    clock(monkeypatch, "2026-10-26T10:00:00+00:00")
    task = client.post("/tasks", json={"title": "Notify fixture", "due": "2026-10-25"}).json()
    feed = client.get("/notifications").json()
    assert feed["unread"] == 1 and not feed["quiet"]
    item = feed["items"][0]
    assert not item["read"]
    assert client.post("/notifications/read", json={"ids": [item["id"]]}).json()["unread"] == 0
    assert client.post("/notifications/read", json={"ids": [item["id"]]}).json()["unread"] == 0
    # A new service instance uses the same persisted database.
    from lifeos.notifications import NotificationService

    assert NotificationService(setup_app[0].state.recommendations).feed()["items"][0]["read"]
    assert (
        client.put(
            f"/tasks/{task['id']}", json={"title": "Changed fixture", "due": "2026-10-25"}
        ).status_code
        == 200
    )
    assert client.get("/notifications").json()["unread"] == 1
    assert client.get("/recommendations").json()["items"]


def test_notifications_bound_bulk_ack_atomicity_categories_and_disabled(client, monkeypatch):
    clock(monkeypatch, "2026-10-26T10:00:00+00:00")
    for index in range(22):
        client.post("/tasks", json={"title": f"Notification {index}", "due": "2026-10-25"})
    feed = client.get("/notifications").json()
    assert len(feed["items"]) == 20 and feed["unread"] == 22 and feed["truncated"]
    valid = feed["items"][0]["id"]
    assert client.post("/notifications/read", json={"ids": [valid, "0" * 64]}).status_code == 409
    assert client.get("/notifications").json()["unread"] == 22
    assert client.post("/notifications/read", json={"ids": []}).status_code == 422
    assert client.post("/notifications/read", json={"ids": [valid] * 21}).status_code == 422
    assert client.put("/notifications/preferences", json={"tasks": False}).json()["items"] == []
    assert (
        client.put("/notifications/preferences", json={"tasks": True, "enabled": False}).json()[
            "unread"
        ]
        == 0
    )
    assert client.put("/notifications/preferences", json={"enabled": True}).json()["unread"] == 22
    assert (
        client.put("/notifications/preferences", json={"quiet_start": "24:01"}).status_code == 422
    )
    assert client.put("/notifications/preferences", json={"unexpected": True}).status_code == 422


@pytest.mark.parametrize(
    "instant,quiet",
    [
        ("2026-10-26T19:59:00+00:00", False),
        ("2026-10-26T20:00:00+00:00", True),
        ("2026-10-27T04:59:00+00:00", True),
        ("2026-10-27T05:00:00+00:00", False),
        ("2026-10-24T22:30:00+00:00", True),
        ("2026-10-24T23:30:00+00:00", True),
    ],
)
def test_notifications_quiet_hours_wall_clock_dst_and_exclusive_end(
    client, monkeypatch, instant, quiet
):
    clock(monkeypatch, instant)
    assert client.get("/notifications").json()["quiet"] is quiet


def test_notifications_equal_quiet_times_daytime_and_workspace_zone(client, monkeypatch):
    clock(monkeypatch, "2026-10-26T10:00:00+00:00")
    assert client.put(
        "/notifications/preferences", json={"quiet_start": "09:00", "quiet_end": "13:00"}
    ).json()["quiet"]
    assert client.put("/settings", json={"timezone": "America/New_York"}).status_code == 200
    assert not client.get("/notifications").json()["quiet"]
    assert client.put(
        "/notifications/preferences", json={"quiet_start": "09:00", "quiet_end": "09:00"}
    ).json()["quiet"]
    assert not client.put("/notifications/preferences", json={"quiet_enabled": False}).json()[
        "quiet"
    ]


def test_notifications_session_csrf_no_inference_and_no_task_mutation(
    client, setup_app, monkeypatch
):
    clock(monkeypatch, "2026-10-26T10:00:00+00:00")
    monkeypatch.setattr(
        setup_app[0].state.assistant, "infer", lambda _: pytest.fail("Notifications cannot infer")
    )
    task = client.post("/tasks", json={"title": "Read only fixture", "due": "2026-10-25"}).json()
    item = client.get("/notifications").json()["items"][0]
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.post("/notifications/read", json={"ids": [item["id"]]}).status_code == 403
    assert client.put("/notifications/preferences", json={"enabled": False}).status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    assert client.post("/notifications/read", json={"ids": [item["id"]]}).status_code == 200
    assert client.get("/tasks").json() == [task]
    with TestClient(
        setup_app[0], base_url="http://127.0.0.1:8000", headers={"X-LifeOS-Key": "test-process-key"}
    ) as other:
        assert other.get("/notifications").status_code == 401


def test_notification_categories_conflicts_and_active_old_reads_are_preserved(client, monkeypatch):
    clock(monkeypatch, "2026-10-26T10:00:00+00:00")
    client.post("/tasks", json={"title": "Long overdue fixture", "due": "2026-10-25"})
    old = client.get("/notifications").json()["items"][0]["id"]
    client.post("/notifications/read", json={"ids": [old]})
    clock(monkeypatch, "2026-11-30T10:00:00+00:00")
    for title, start, end in [("A", "11:00", "12:00"), ("B", "11:30", "12:30")]:
        client.post(
            "/events",
            json={
                "title": title,
                "start": f"2026-11-30T{start}:00Z",
                "end": f"2026-11-30T{end}:00Z",
            },
        )
    feed = client.get("/notifications").json()
    assert feed["unread"] == 1
    conflict = next(item for item in feed["items"] if item["kind"] == "conflict")
    client.post("/notifications/read", json={"ids": [conflict["id"]]})
    assert client.get("/notifications").json()["unread"] == 0
    assert (
        len(client.put("/notifications/preferences", json={"conflicts": False}).json()["items"])
        == 1
    )
    assert client.put("/notifications/preferences", json={"tasks": False}).json()["items"] == []


def test_concurrent_partial_notification_preferences_do_not_undo_other_fields(client, setup_app):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from lifeos.notifications import NotificationService, Preferences
    from sqlalchemy import event

    service = NotificationService(setup_app[0].state.recommendations)
    client.put("/notifications/preferences", json={})
    barrier = Barrier(2)

    def synchronize(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO notification_preferences"):
            barrier.wait(timeout=5)

    event.listen(service.engine, "before_cursor_execute", synchronize)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(service.save_preferences, Preferences(tasks=False))
            second = pool.submit(service.save_preferences, Preferences(quiet_start="21:00"))
            first.result(timeout=10)
            second.result(timeout=10)
    finally:
        event.remove(service.engine, "before_cursor_execute", synchronize)
    preferences = client.get("/notifications").json()["preferences"]
    assert preferences["tasks"] is False and preferences["quiet_start"] == "21:00"


def test_notification_snooze_expiry_dismiss_restore_and_source_versions(client, monkeypatch):
    clock(monkeypatch, "2026-10-26T10:00:00+00:00")
    task = client.post("/tasks", json={"title": "Snooze fixture", "due": "2026-10-25"}).json()
    id = client.get("/notifications").json()["items"][0]["id"]
    client.post("/notifications/read", json={"ids": [id]})
    feed = client.post(
        "/notifications/action", json={"id": id, "action": "snooze", "minutes": 60}
    ).json()
    assert feed["items"] == [] and feed["unread"] == 0 and feed["hidden_total"] == 1
    assert feed["hidden"][0]["snoozed_until"] == int(
        datetime(2026, 10, 26, 11, tzinfo=timezone.utc).timestamp()
    )
    clock(monkeypatch, "2026-10-26T10:59:59+00:00")
    assert client.get("/notifications").json()["items"] == []
    clock(monkeypatch, "2026-10-26T11:00:00+00:00")
    feed = client.get("/notifications").json()
    assert feed["unread"] == 1 and feed["hidden_total"] == 0
    assert (
        client.post("/notifications/action", json={"id": id, "action": "dismiss"}).json()["items"]
        == []
    )
    assert client.get("/notifications").json()["hidden"][0]["dismissed"]
    assert (
        client.post("/notifications/action", json={"id": id, "action": "restore"}).json()["unread"]
        == 1
    )
    client.post("/notifications/action", json={"id": id, "action": "dismiss"})
    client.put(
        f"/tasks/{task['id']}", json={"title": "Changed snooze fixture", "due": "2026-10-25"}
    )
    assert client.get("/notifications").json()["unread"] == 1
    assert client.get("/notifications").json()["hidden_total"] == 0


def test_notification_actions_validation_csrf_and_no_task_mutation(client, monkeypatch):
    clock(monkeypatch, "2026-10-26T10:00:00+00:00")
    task = client.post("/tasks", json={"title": "Action fixture", "due": "2026-10-25"}).json()
    id = client.get("/notifications").json()["items"][0]["id"]
    for body in [
        {"action": "snooze"},
        {"action": "snooze", "minutes": 5},
        {"action": "dismiss", "minutes": 60},
        {"action": "unknown"},
    ]:
        assert client.post("/notifications/action", json={"id": id, **body}).status_code == 422
    assert (
        client.post("/notifications/action", json={"id": "0" * 64, "action": "dismiss"}).status_code
        == 409
    )
    csrf = client.headers.pop("X-CSRF-Token")
    assert (
        client.post("/notifications/action", json={"id": id, "action": "dismiss"}).status_code
        == 403
    )
    client.headers["X-CSRF-Token"] = csrf
    client.post("/notifications/read", json={"ids": [id]})
    client.post("/notifications/action", json={"id": id, "action": "dismiss"})
    assert (
        client.post("/notifications/action", json={"id": id, "action": "restore"}).json()["unread"]
        == 0
    )
    assert client.get("/tasks").json() == [task]


def test_stale_tab_cannot_mark_a_snoozed_notification_read_before_expiry(client, monkeypatch):
    clock(monkeypatch, "2026-10-26T10:00:00+00:00")
    client.post("/tasks", json={"title": "Stale tab fixture", "due": "2026-10-25"})
    id = client.get("/notifications").json()["items"][0]["id"]
    assert (
        client.post(
            "/notifications/action", json={"id": id, "action": "snooze", "minutes": 15}
        ).status_code
        == 200
    )
    assert client.post("/notifications/read", json={"ids": [id]}).status_code == 409
    clock(monkeypatch, "2026-10-26T10:15:00+00:00")
    assert client.get("/notifications").json()["unread"] == 1


def test_notification_action_migration_preserves_existing_preferences_and_read_state(tmp_path):
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from lifeos.db import migrate, open_database
    from sqlalchemy import text

    engine = open_database(tmp_path)
    cfg = Config()
    cfg.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "services/api/alembic")
    )
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0009")
        connection.execute(
            text(
                "INSERT INTO notification_preferences(id,enabled,tasks,conflicts,quiet_enabled,quiet_start,quiet_end) VALUES(1,1,0,1,1,'21:00','06:00')"
            )
        )
        connection.execute(
            text("INSERT INTO notification_reads(id,read_at) VALUES(:id,42)"), {"id": "a" * 64}
        )
    migrate(engine)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT tasks,quiet_start FROM notification_preferences")
        ).one() == (0, "21:00")
        assert connection.scalar(text("SELECT read_at FROM notification_reads")) == 42
        assert connection.scalar(text("SELECT count(*) FROM notification_actions")) == 0
    engine.dispose()
