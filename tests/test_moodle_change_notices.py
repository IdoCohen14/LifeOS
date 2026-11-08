import json
from datetime import datetime, timezone


def test_moodle_change_notices_use_observed_versions_and_require_calendar_opt_in(
    client, setup_app, monkeypatch
):
    from lifeos import notifications
    from lifeos.moodle_changes import MoodleChange
    from sqlalchemy.orm import Session

    now = datetime(2026, 10, 29, 10, tzinfo=timezone.utc)
    monkeypatch.setattr(notifications, "current_time", lambda: now)
    previous = {
        "title": "Exam fixture",
        "start": "2026-11-01",
        "end": "2026-11-02",
        "all_day": True,
        "source_url": None,
    }
    current = {**previous, "start": "2026-11-02", "end": "2026-11-03"}
    with Session(setup_app[0].state.assistant.engine) as db:
        db.add(
            MoodleChange(
                id="change-fixture",
                event_id="source-fixture",
                kind="changed",
                previous=json.dumps(previous),
                current=json.dumps(current),
                observed_at=int(now.timestamp()),
            )
        )
        db.commit()
    assert not any(
        item["kind"] == "moodle_update" for item in client.get("/notifications").json()["items"]
    )
    feed = client.put("/notifications/preferences", json={"events": True}).json()
    items = [item for item in feed["items"] if item["kind"] == "moodle_update"]
    assert len(items) == 1
    item = items[0]
    assert (
        item["change_kind"] == "changed"
        and item["previous_start"] == "2026-11-01"
        and item["start"] == "2026-11-02"
    )
    assert item["observed_at"] == int(now.timestamp())
    response = client.post("/notifications/read", json={"ids": [item["id"]]})
    assert response.status_code == 200
    assert (
        next(row for row in response.json()["items"] if row["kind"] == "moodle_update")["read"]
        is True
    )
    assert len(client.get("/integrations/moodle/changes").json()) == 1
