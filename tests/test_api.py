from fastapi.testclient import TestClient


def test_rejects_unauthenticated_and_forged_requests(setup_app):
    app, _, _ = setup_app
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        assert c.get("/tasks").status_code == 403
        c.headers["X-LifeOS-Key"] = "test-process-key"
        assert c.get("/tasks").status_code == 401
        assert c.post("/session", json={"password": "wrong"}).status_code == 401
        c.cookies.set("lifeos_session", "forged", domain="127.0.0.1", path="/")
        assert c.get("/tasks").status_code == 401


def test_task_crud_and_validation(client):
    assert client.post("/tasks", json={"title": "   "}).status_code == 422
    assert client.post("/tasks", json={"title": "x", "priority": "invented"}).status_code == 422
    task = client.post("/tasks", json={"title": "ללמוד אלגברה", "priority": "high"}).json()
    assert task["completed"] is False
    assert len(client.get("/tasks").json()) == 1
    updated = client.put(f"/tasks/{task['id']}", json={**task, "completed": True})
    assert updated.status_code == 200
    assert updated.json()["completed"] is True
    assert client.delete(f"/tasks/{task['id']}").status_code == 204
    assert client.get("/tasks").json() == []
    assert client.delete(f"/tasks/{task['id']}").status_code == 404


def test_events_validate_timezone_and_date_only(client):
    timed = {
        "title": "מפגש",
        "start": "2026-10-25T10:00:00+02:00",
        "end": "2026-10-25T11:00:00+02:00",
        "all_day": False,
    }
    r = client.post("/events", json=timed)
    assert r.status_code == 201
    assert r.json()["start"] == "2026-10-25T08:00:00Z"
    assert client.post("/events", json={**timed, "end": timed["start"]}).status_code == 422
    assert client.post("/events", json={**timed, "start": "2026-10-25T10:00:00"}).status_code == 422
    day = client.post(
        "/events",
        json={"title": "חופש", "start": "2026-10-25", "end": "2026-10-26", "all_day": True},
    )
    assert day.status_code == 201
    assert day.json()["start"] == "2026-10-25"
    assert client.put("/settings", json={"timezone": "Mars/Olympus"}).status_code == 422


def test_csrf_and_origin_protection(client):
    assert (
        client.post("/tasks", headers={"X-CSRF-Token": ""}, json={"title": "bad"}).status_code
        == 403
    )
    assert (
        client.post(
            "/tasks", headers={"Origin": "https://evil.example"}, json={"title": "bad"}
        ).status_code
        == 403
    )
    assert client.get("/tasks", headers={"Host": "evil.example"}).status_code == 400


def test_restart_persists_and_migrations_are_idempotent(client, setup_app):
    _, path, create_app = setup_app
    client.post("/tasks", json={"title": "persist me"})
    assert (
        client.put("/settings", json={"display_name": "עידו", "theme": "light"}).status_code == 200
    )
    with TestClient(
        create_app(), base_url="http://127.0.0.1:8000", headers={"X-LifeOS-Key": "test-process-key"}
    ) as other:
        result = other.post("/session", json={"password": "correct horse battery staple"})
        assert result.status_code == 200
        assert other.get("/tasks").json()[0]["title"] == "persist me"
        assert other.get("/settings").json()["display_name"] == "עידו"
    assert (path / "lifeos.sqlite3").exists()


def test_logout_invalidates_session(client):
    assert client.delete("/session").status_code == 204
    assert client.get("/tasks").status_code == 401


def test_fractional_second_interval_is_valid(client):
    response = client.post(
        "/events",
        json={
            "title": "short interval",
            "start": "2026-10-25T10:00:00Z",
            "end": "2026-10-25T10:00:00.500Z",
        },
    )
    assert response.status_code == 201


def test_password_is_hashed_and_sessions_expire(client, setup_app):
    from lifeos.db import open_database
    from lifeos.models import LoginSession
    from sqlalchemy import update
    from sqlalchemy.orm import Session

    _, path, _ = setup_app
    assert "correct horse battery staple" not in (path / "auth.json").read_text()
    engine = open_database(path)
    with Session(engine) as db:
        db.execute(update(LoginSession).values(expires=0))
        db.commit()
    engine.dispose()
    assert client.get("/tasks").status_code == 401
