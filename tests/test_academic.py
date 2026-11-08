def course_fixture(client):
    term = client.post(
        "/academic/terms",
        json={"name": "סמסטר א", "start_date": "2026-10-01", "end_date": "2027-02-01"},
    )
    assert term.status_code == 201
    course = client.post(
        "/academic/courses", json={"name": "אלגברה", "term_id": term.json()["id"], "credits": 4}
    )
    assert course.status_code == 201
    return term.json(), course.json()


def test_academic_crud_links_tasks_and_preserves_completion(client):
    term, course = course_fixture(client)
    result = client.post(
        "/academic/items",
        json={
            "course_id": course["id"],
            "title": "תרגיל 1",
            "kind": "assignment",
            "due": "2026-11-02",
        },
    )
    assert result.status_code == 201
    item = result.json()
    task = client.get("/tasks").json()[0]
    assert task["academic_id"] == item["id"]
    assert client.put(f"/tasks/{task['id']}", json={**task, "completed": True}).status_code == 200
    assert client.get("/academic/items").json()[0]["completed"] is True
    changed = client.put(
        f"/academic/items/{item['id']}", json={**item, "due": "2026-11-04", "completed": True}
    )
    assert changed.status_code == 200
    assert client.get("/tasks").json()[0]["due"] == "2026-11-04"
    assert client.delete(f"/tasks/{task['id']}").status_code == 409
    assert client.delete(f"/academic/courses/{course['id']}").status_code == 409
    assert client.delete(f"/academic/terms/{term['id']}").status_code == 409
    assert client.delete(f"/academic/items/{item['id']}").status_code == 204
    assert client.get("/tasks").json() == []
    assert client.delete(f"/academic/courses/{course['id']}").status_code == 204
    assert client.delete(f"/academic/terms/{term['id']}").status_code == 204


def test_timetable_calendar_and_grade_validation(client):
    _, course = course_fixture(client)
    slot = client.post(
        "/academic/timetable",
        json={
            "course_id": course["id"],
            "weekday": 0,
            "start_time": "10:00",
            "end_time": "12:00",
            "timezone": "Asia/Jerusalem",
            "location": "בניין 4",
        },
    )
    assert slot.status_code == 201
    events = client.get("/academic/calendar").json()
    assert events
    assert events[0]["source"] == "timetable"
    assert events[0]["course_id"] == course["id"]
    assert all(event["start"] >= "2026-10-01" and event["start"] < "2027-02-02" for event in events)
    assert (
        client.post("/academic/timetable", json={**slot.json(), "end_time": "09:00"}).status_code
        == 422
    )
    assert (
        client.post(
            "/academic/grades",
            json={"course_id": course["id"], "title": "מבחן", "score": 101, "maximum": 100},
        ).status_code
        == 422
    )
    grade = client.post(
        "/academic/grades",
        json={
            "course_id": course["id"],
            "title": "מבחן",
            "score": 90,
            "maximum": 100,
            "weight": 100,
        },
    )
    assert grade.status_code == 201
    assert client.get("/academic/grades").json()[0]["score"] == 90
    assert (
        client.post("/academic/courses", json={"term_id": "missing", "name": "bad"}).status_code
        == 404
    )


def test_unauthenticated_academics(setup_app):
    from fastapi.testclient import TestClient

    app, _, _ = setup_app
    with TestClient(
        app, base_url="http://127.0.0.1:8000", headers={"X-LifeOS-Key": "test-process-key"}
    ) as unauth:
        assert unauth.get("/academic/courses").status_code == 401


def test_rejects_dst_ambiguous_timetable_and_overweight_grades(client):
    _, course = course_fixture(client)
    assert (
        client.post(
            "/academic/timetable",
            json={
                "course_id": course["id"],
                "weekday": 0,
                "start_time": "01:30",
                "end_time": "03:00",
                "timezone": "Asia/Jerusalem",
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/academic/grades",
            json={
                "course_id": course["id"],
                "title": "part A",
                "score": 45,
                "maximum": 50,
                "weight": 60,
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/academic/grades",
            json={
                "course_id": course["id"],
                "title": "part B",
                "score": 20,
                "maximum": 50,
                "weight": 60,
            },
        ).status_code
        == 422
    )


def test_phase_a_database_upgrades_without_losing_existing_data(tmp_path):
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
        command.upgrade(cfg, "0001")
        connection.execute(
            text(
                "INSERT INTO tasks(id,title,notes,priority,due,completed,created_at) VALUES('old','Phase A saved task','','medium',NULL,0,'2026-10-25T00:00:00Z')"
            )
        )
    migrate(engine)
    migrate(engine)
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT title FROM tasks WHERE id='old'"))
            == "Phase A saved task"
        )
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0044"
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
    engine.dispose()
