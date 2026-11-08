import hashlib
from datetime import datetime, timezone


def frozen(monkeypatch):
    from lifeos import notifications, recommendations

    now = datetime(2026, 10, 27, 10, tzinfo=timezone.utc)
    monkeypatch.setattr(notifications, "current_time", lambda: now)
    monkeypatch.setattr(recommendations, "current_time", lambda: now)
    return now


def test_notification_metadata_queries_only_current_ids_and_preserves_unrelated_rows(
    client, setup_app, monkeypatch
):
    from lifeos.notification_models import NotificationAction, NotificationRead
    from sqlalchemy import event, func, insert, select
    from sqlalchemy.orm import Session

    frozen(monkeypatch)
    client.post("/tasks", json={"title": "Metadata fixture", "due": "2026-10-27"})
    engine = setup_app[0].state.assistant.engine
    with Session(engine) as db:
        rows = [
            {"id": hashlib.sha256(f"Unrelated fixture {i}".encode()).hexdigest(), "read_at": 0}
            for i in range(1000)
        ]
        db.execute(insert(NotificationRead), rows)
        db.execute(
            insert(NotificationAction),
            [
                {"id": row["id"], "dismissed": False, "snoozed_until": None, "updated_at": 0}
                for row in rows
            ],
        )
        db.commit()
    queries = []

    def observed(connection, cursor, statement, parameters, context, many):
        normalized = " ".join(statement.split())
        if normalized.startswith("SELECT") and any(
            "FROM " + table in normalized
            for table in ("notification_reads", "notification_actions")
        ):
            queries.append((normalized, parameters))

    event.listen(engine, "before_cursor_execute", observed)
    try:
        response = client.get("/notifications")
    finally:
        event.remove(engine, "before_cursor_execute", observed)
    assert response.status_code == 200 and response.json()["unread"] == 1
    assert len(queries) == 2
    assert all(" IN (" in query and len(parameters) == 1 for query, parameters in queries)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(NotificationRead)) == 1000
        assert db.scalar(select(func.count()).select_from(NotificationAction)) == 1000


def test_notification_feed_budget_rejects_partial_result(client, monkeypatch):
    from types import SimpleNamespace

    from lifeos import notifications

    frozen(monkeypatch)
    client.post("/tasks", json={"title": "Budget fixture", "due": "2026-10-27"})
    values = iter([0, 20])
    monkeypatch.setattr(
        notifications, "time", SimpleNamespace(monotonic=lambda: next(values, 20)), raising=False
    )
    response = client.get("/notifications")
    assert response.status_code == 503
    assert response.json() == {"detail": "notifications_resource_limit"}


def test_notification_metadata_batches_after_hidden_prefix_and_empty_feed(
    client, setup_app, monkeypatch
):
    from lifeos.models import Task
    from lifeos.notification_models import NotificationAction, NotificationRead
    from sqlalchemy import event, insert
    from sqlalchemy.orm import Session

    frozen(monkeypatch)
    engine = setup_app[0].state.assistant.engine
    assert client.get("/notifications").json()["unread"] == 0
    with Session(engine) as db:
        db.execute(
            insert(Task),
            [
                {
                    "id": str(index),
                    "title": f"Batch fixture {index}",
                    "due": "2026-10-27",
                    "priority": "high",
                    "notes": "",
                    "completed": False,
                    "created_at": "2026-10-27T00:00:00Z",
                }
                for index in range(505)
            ],
        )
        db.commit()
    candidates, _ = setup_app[0].state.recommendations.candidates()
    assert len(candidates) == 505
    with Session(engine) as db:
        db.execute(
            insert(NotificationAction),
            [
                {"id": row["id"], "dismissed": True, "snoozed_until": None, "updated_at": 0}
                for row in candidates[:500]
            ],
        )
        db.execute(insert(NotificationRead), [{"id": candidates[500]["id"], "read_at": 0}])
        db.commit()
    parameters_seen = []

    def observed(connection, cursor, statement, parameters, context, many):
        if (
            statement.startswith("SELECT")
            and "FROM notification_" in statement
            and " IN (" in statement
        ):
            parameters_seen.append(len(parameters))

    event.listen(engine, "before_cursor_execute", observed)
    try:
        feed = client.get("/notifications").json()
    finally:
        event.remove(engine, "before_cursor_execute", observed)
    assert parameters_seen == [500, 500, 5, 5]
    assert feed["unread"] == 4 and feed["hidden_total"] == 500 and feed["hidden_truncated"]
    assert [row["id"] for row in feed["items"]] == [row["id"] for row in candidates[501:]] + [
        candidates[500]["id"]
    ]


def test_notification_deadline_during_metadata_returns_no_partial_feed(
    client, setup_app, monkeypatch
):
    from types import SimpleNamespace

    from lifeos import notifications
    from sqlalchemy import event

    frozen(monkeypatch)
    client.post("/tasks", json={"title": "Batch expiry fixture", "due": "2026-10-27"})
    clock = [0]
    monkeypatch.setattr(notifications, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    def observed(connection, cursor, statement, parameters, context, many):
        if statement.startswith("SELECT") and "FROM notification_actions" in statement:
            clock[0] = 20

    engine = setup_app[0].state.assistant.engine
    event.listen(engine, "after_cursor_execute", observed)
    try:
        response = client.get("/notifications")
    finally:
        event.remove(engine, "after_cursor_execute", observed)
    assert response.status_code == 503 and response.json() == {
        "detail": "notifications_resource_limit"
    }
