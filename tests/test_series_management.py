from datetime import datetime, timezone


def weekly(client, monkeypatch):
    from lifeos import recurring_events, series_management

    now = datetime(2026, 10, 27, 6, tzinfo=timezone.utc)
    monkeypatch.setattr(recurring_events, "current_time", lambda: now)
    monkeypatch.setattr(series_management, "current_time", lambda: now)
    preview = client.post(
        "/recurrence/preview",
        json={
            "title": "Managed weekly fixture",
            "day": "2026-10-28",
            "clock": "09:00",
            "duration": 60,
            "count": 3,
            "all_day": False,
            "timezone": "Asia/Jerusalem",
        },
    ).json()
    result = client.post("/recurrence/confirm", json={"id": preview["id"]})
    assert result.status_code == 200
    return result.json()


def test_series_preview_protects_edited_and_confirmation_deletes_only_reviewed(client, monkeypatch):
    saved = weekly(client, monkeypatch)
    series = client.get("/recurrence/series").json()["items"]
    assert len(series) == 1 and series[0]["id"] == saved["series_id"]
    events = client.get("/events").json()
    edited = client.put(
        "/events/" + events[1]["id"], json={**events[1], "title": "Individually edited fixture"}
    ).json()
    preview = client.post(
        f"/recurrence/series/{saved['series_id']}/deletion-preview",
        json={"from_day": "2026-10-27", "include_modified": False},
    )
    assert preview.status_code == 200
    plan = preview.json()
    assert len(plan["events"]) == 2 and plan["skipped_modified"] == 1
    assert len(client.get("/events").json()) == 3
    response = client.post("/recurrence/deletions/confirm", json={"id": plan["id"]})
    assert response.status_code == 200 and response.json()["deleted_count"] == 2
    assert client.get("/events").json() == [edited]
    assert (
        client.post("/recurrence/deletions/confirm", json={"id": plan["id"]}).json()
        == response.json()
    )
    client.delete("/events/" + edited["id"])
    assert client.get("/recurrence/series").json()["items"] == []


def test_series_delete_rejects_source_change_and_cancelled_preview(client, monkeypatch):
    saved = weekly(client, monkeypatch)
    plan = client.post(
        f"/recurrence/series/{saved['series_id']}/deletion-preview",
        json={"from_day": "2026-10-27", "include_modified": True},
    ).json()
    event = client.get("/events").json()[0]
    client.put("/events/" + event["id"], json={**event, "notes": "Changed after review fixture"})
    assert client.post("/recurrence/deletions/confirm", json={"id": plan["id"]}).status_code == 409
    assert len(client.get("/events").json()) == 3
    assert client.delete("/recurrence/deletions/" + plan["id"]).status_code == 204
    assert client.post("/recurrence/deletions/confirm", json={"id": plan["id"]}).status_code == 404


def test_series_deletion_rolls_back_all_events_links_and_metadata_after_flush(
    client, setup_app, monkeypatch
):
    from fastapi import HTTPException
    from lifeos import series_management
    from sqlalchemy import event

    saved = weekly(client, monkeypatch)
    plan = client.post(
        f"/recurrence/series/{saved['series_id']}/deletion-preview", json={"from_day": "2026-10-27"}
    ).json()
    engine = setup_app[0].state.assistant.engine
    flushed = []

    def observed(connection, cursor, statement, parameters, context, many):
        if statement.startswith("DELETE FROM events"):
            flushed.append(True)

    original = series_management.budget

    def expired(deadline):
        if flushed:
            raise HTTPException(503, "series_resource_limit")
        original(deadline)

    event.listen(engine, "after_cursor_execute", observed)
    monkeypatch.setattr(series_management, "budget", expired)
    try:
        assert (
            client.post("/recurrence/deletions/confirm", json={"id": plan["id"]}).status_code == 503
        )
    finally:
        event.remove(engine, "after_cursor_execute", observed)
    assert flushed and len(client.get("/events").json()) == 3
    assert client.get("/recurrence/series").json()["items"][0]["count"] == 3
    monkeypatch.setattr(series_management, "budget", original)
    assert (
        client.post("/recurrence/deletions/confirm", json={"id": plan["id"]}).json()[
            "deleted_count"
        ]
        == 3
    )
    assert client.get("/recurrence/series").json()["items"] == []


def test_legacy_approved_mapping_migration_preserves_events_and_marks_original_unknown(
    client, setup_app, monkeypatch
):
    import json

    from alembic import command
    from alembic.config import Config
    from lifeos.db import ROOT, migrate
    from sqlalchemy import text

    saved = weekly(client, monkeypatch)
    engine = setup_app[0].state.assistant.engine
    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "services/api/alembic"))
    assert (
        client.post(
            "/events",
            json={
                "title": "Unrelated same title fixture",
                "start": "2026-10-28T09:00:00+02:00",
                "end": "2026-10-28T10:00:00+02:00",
            },
        ).status_code
        == 201
    )
    before = client.get("/events").json()
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.downgrade(cfg, "0018")
        connection.execute(
            text("UPDATE recurrence_proposals SET payload=:body WHERE id=:id"),
            {
                "id": saved["series_id"],
                "body": json.dumps(
                    {"title": "Legacy approved fixture", "timezone": "Asia/Jerusalem"}
                ),
            },
        )
    migrate(engine)
    assert client.get("/events").json() == before
    rows = client.get("/recurrence/series").json()["items"]
    assert len(rows) == 1 and rows[0]["count"] == 3
    protected = client.post(
        f"/recurrence/series/{saved['series_id']}/deletion-preview", json={"from_day": "2026-10-27"}
    ).json()
    assert protected["events"] == [] and protected["skipped_modified"] == 3
    included = client.post(
        f"/recurrence/series/{saved['series_id']}/deletion-preview",
        json={"from_day": "2026-10-27", "include_modified": True},
    ).json()
    assert len(included["events"]) == 3 and all(row["unknown"] for row in included["events"])
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT payload FROM recurrence_proposals WHERE id=:id"),
                {"id": saved["series_id"]},
            )
            == "{}"
        )


def test_series_delete_session_csrf_expiry_and_date_boundaries(client, setup_app, monkeypatch):
    from lifeos.series_models import SeriesDeleteProposal
    from sqlalchemy.orm import Session

    saved = weekly(client, monkeypatch)
    url = f"/recurrence/series/{saved['series_id']}/deletion-preview"
    assert client.post(url, json={"from_day": "2026-10-26"}).status_code == 422
    plan = client.post(url, json={"from_day": "2026-11-04"}).json()
    assert len(plan["events"]) == 2
    token = client.headers.pop("X-CSRF-Token")
    assert client.post("/recurrence/deletions/confirm", json={"id": plan["id"]}).status_code == 403
    client.headers["X-CSRF-Token"] = token
    with Session(setup_app[0].state.assistant.engine) as db:
        db.get(SeriesDeleteProposal, plan["id"]).expires = 0
        db.commit()
    assert client.post("/recurrence/deletions/confirm", json={"id": plan["id"]}).status_code == 404
    other = client.post(url, json={"from_day": "2026-10-27"}).json()
    session = client.post("/session", json={"password": "correct horse battery staple"}).json()
    client.headers["X-CSRF-Token"] = session["csrf"]
    assert client.post("/recurrence/deletions/confirm", json={"id": other["id"]}).status_code == 404
    assert len(client.get("/events").json()) == 3


def test_series_all_day_midnight_crossing_after_delete_flush_rolls_back(
    client, setup_app, monkeypatch
):
    from datetime import datetime, timezone

    from lifeos import recurring_events, series_management
    from sqlalchemy import event

    clock = [datetime(2026, 10, 27, 21, 59, 59, tzinfo=timezone.utc)]
    monkeypatch.setattr(recurring_events, "current_time", lambda: clock[0])
    monkeypatch.setattr(series_management, "current_time", lambda: clock[0])
    created = client.post(
        "/recurrence/preview",
        json={
            "title": "Midnight all-day fixture",
            "day": "2026-10-27",
            "count": 2,
            "all_day": True,
            "timezone": "Asia/Jerusalem",
        },
    ).json()
    saved = client.post("/recurrence/confirm", json={"id": created["id"]}).json()
    plan = client.post(
        f"/recurrence/series/{saved['series_id']}/deletion-preview", json={"from_day": "2026-10-27"}
    ).json()
    engine = setup_app[0].state.assistant.engine

    def crossed(connection, cursor, statement, parameters, context, many):
        if statement.startswith("DELETE FROM events"):
            clock[0] = datetime(2026, 10, 27, 22, 0, 0, tzinfo=timezone.utc)

    event.listen(engine, "after_cursor_execute", crossed)
    try:
        assert (
            client.post("/recurrence/deletions/confirm", json={"id": plan["id"]}).status_code == 409
        )
    finally:
        event.remove(engine, "after_cursor_execute", crossed)
    assert len(client.get("/events").json()) == 2
