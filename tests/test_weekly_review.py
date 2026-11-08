from datetime import datetime, timedelta, timezone


def test_weekly_review_tracks_actual_transitions_and_ignores_unchanged_updates(client):
    task = client.post("/tasks", json={"title": "Review fixture", "completed": True}).json()
    client.put(f"/tasks/{task['id']}", json={"title": task["title"], "completed": True})
    client.put(f"/tasks/{task['id']}", json={"title": task["title"], "completed": False})
    client.put(f"/tasks/{task['id']}", json={"title": task["title"], "completed": True})
    response = client.get("/review/weekly")
    assert response.status_code == 200
    review = response.json()
    assert review["completed"] == 1 and review["reopened"] == 1 and review["unknown_completed"] == 0
    assert review["transition_count"] == 3
    assert sum(day["completed"] for day in review["days"]) == 1
    assert review["recent"][0]["currently_completed"]
    assert datetime.fromisoformat(
        review["tracking_started_at"].replace("Z", "+00:00")
    ).utcoffset() == timedelta(0)


def test_weekly_review_linked_academic_path_and_deletion_preserve_privacy(client):
    from test_academic import course_fixture

    _, course = course_fixture(client)
    item = client.post(
        "/academic/items",
        json={
            "course_id": course["id"],
            "title": "Linked review fixture",
            "kind": "assignment",
            "due": "2026-10-28",
        },
    ).json()
    client.put(f"/academic/items/{item['id']}", json={**item, "completed": True})
    assert client.get("/review/weekly").json()["completed"] == 1
    client.delete(f"/academic/items/{item['id']}")
    review = client.get("/review/weekly").json()
    assert review["completed"] == 0 and review["recent"] == []


def test_weekly_review_rollback_does_not_publish_history(client, setup_app):
    from lifeos.models import Task
    from sqlalchemy.orm import Session

    task = client.post("/tasks", json={"title": "Rollback review fixture"}).json()
    with Session(setup_app[0].state.recommendations.engine) as db:
        db.get(Task, task["id"]).completed = True
        db.flush()
        db.rollback()
    assert client.get("/review/weekly").json()["transition_count"] == 0
    assert not client.get("/tasks").json()[0]["completed"]


def test_weekly_review_dst_bounds_and_unique_period_counts(client, setup_app, monkeypatch):
    from lifeos import weekly_review
    from sqlalchemy import text

    monkeypatch.setattr(
        weekly_review, "current_time", lambda: datetime(2026, 10, 26, 10, tzinfo=timezone.utc)
    )
    tasks = [
        client.post("/tasks", json={"title": f"Boundary review {index}"}).json()
        for index in range(3)
    ]
    with setup_app[0].state.recommendations.engine.begin() as db:
        db.execute(
            text("UPDATE task_history_metadata SET tracking_started_at='2026-10-01T00:00:00.000Z'")
        )
        for id, task, timestamp in [
            ("a", tasks[0], "2026-10-24T21:00:00.000Z"),
            ("b", tasks[1], "2026-10-24T23:30:00.000Z"),
            ("c", tasks[2], "2026-10-25T22:00:00.000Z"),
            ("d", tasks[0], "2026-10-23T10:00:00.000Z"),
        ]:
            db.execute(
                text(
                    "INSERT INTO task_status_history(id,task_id,completed,occurred_at) VALUES(:id,:task,1,:time)"
                ),
                {"id": id, "task": task["id"], "time": timestamp},
            )
    review = client.get("/review/weekly?end=2026-10-25").json()
    assert review["completed"] == 2 and review["transition_count"] == 3
    assert review["days"][-1]["completed"] == 2
    assert sum(day["completed"] for day in review["days"]) == 3
    assert not review["days"][-1]["partial"]


def test_weekly_review_limits_date_validation_and_no_read_mutation(client, monkeypatch):
    from lifeos import weekly_review

    task = client.post("/tasks", json={"title": "Limit review fixture", "completed": True}).json()
    for query in ["end=2026-02-30", "end=2026-10-26T00:00:00Z", "end=1900-01-01", "end=2200-01-01"]:
        assert client.get("/review/weekly?" + query).status_code == 422
    monkeypatch.setattr(weekly_review, "MAX_HISTORY", 0)
    assert client.get("/review/weekly").status_code == 503
    assert client.get("/tasks").json() == [task]
    client.cookies.clear()
    assert client.get("/review/weekly").status_code == 401


def test_weekly_review_upgrade_keeps_old_completed_tasks_without_inventing_dates(tmp_path):
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from lifeos.db import migrate, open_database
    from lifeos.weekly_review import WeeklyReviewService
    from sqlalchemy import text

    engine = open_database(tmp_path)
    cfg = Config()
    cfg.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "services/api/alembic")
    )
    with engine.begin() as db:
        cfg.attributes["connection"] = db
        command.upgrade(cfg, "0012")
        db.execute(
            text(
                "INSERT INTO tasks(id,title,notes,priority,due,completed,created_at) VALUES('old','Old complete fixture','','medium',NULL,1,'2020-01-01T00:00:00Z')"
            )
        )
        db.execute(
            text(
                "INSERT INTO settings(id,display_name,language,theme,timezone) VALUES(1,'','he','dark','Asia/Jerusalem')"
            )
        )
    migrate(engine)
    result = WeeklyReviewService(engine).review()
    assert result["unknown_completed"] == 1
    assert result["completed"] == 0 and result["recent"] == []
    assert sum(row["completed"] for row in result["days"]) == 0
    engine.dispose()


def test_weekly_review_prunes_old_status_rows_only_on_new_transition(client, setup_app):
    from sqlalchemy import text

    task = client.post("/tasks", json={"title": "Retention fixture"}).json()
    old = (
        (datetime.now(timezone.utc) - timedelta(days=100))
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    engine = setup_app[0].state.recommendations.engine
    with engine.begin() as db:
        db.execute(
            text("INSERT INTO task_status_history VALUES('old',:task,1,:time)"),
            {"task": task["id"], "time": old},
        )
    client.put(f"/tasks/{task['id']}", json={"title": task["title"], "completed": True})
    with engine.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM task_status_history WHERE id='old'")) == 0
        assert db.scalar(text("SELECT count(*) FROM task_status_history")) == 1


def test_weekly_review_retention_boundary_is_partial_after_fall_dst(client, setup_app, monkeypatch):
    from lifeos import weekly_review
    from sqlalchemy import text

    monkeypatch.setattr(
        weekly_review, "current_time", lambda: datetime(2026, 10, 26, 21, 30, tzinfo=timezone.utc)
    )
    task = client.post("/tasks", json={"title": "Retention boundary fixture"}).json()
    with setup_app[0].state.recommendations.engine.begin() as db:
        db.execute(
            text("UPDATE task_history_metadata SET tracking_started_at='2026-06-01T00:00:00.000Z'")
        )
        for id, timestamp in [
            ("before", "2026-07-28T21:15:00.000Z"),
            ("after", "2026-07-28T21:45:00.000Z"),
        ]:
            db.execute(
                text("INSERT INTO task_status_history VALUES(:id,:task,1,:time)"),
                {"id": id, "task": task["id"], "time": timestamp},
            )
    result = client.get("/review/weekly?end=2026-08-04").json()
    assert result["range_start"] == "2026-07-29"
    assert result["days"][0]["partial"]
    assert result["transition_count"] == 1
