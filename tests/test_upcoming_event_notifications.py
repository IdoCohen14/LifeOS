import json
from datetime import datetime, timezone


def test_upcoming_event_notices_are_opt_in_and_use_actual_calendar_sources(
    client, setup_app, monkeypatch
):
    from lifeos import notifications
    from lifeos.moodle_models import MoodleEvent
    from sqlalchemy.orm import Session

    now = datetime(2026, 10, 29, 10, tzinfo=timezone.utc)
    monkeypatch.setattr(notifications, "current_time", lambda: now)
    event = client.post(
        "/events",
        json={
            "title": "Meeting fixture",
            "start": "2026-10-29T13:00:00+02:00",
            "end": "2026-10-29T14:00:00+02:00",
        },
    ).json()
    for title, start, end in [
        ("Past fixture", "2026-10-29T11:59:00+02:00", "2026-10-29T12:30:00+02:00"),
        ("Boundary fixture", "2026-10-30T12:00:00+02:00", "2026-10-30T13:00:00+02:00"),
    ]:
        assert (
            client.post("/events", json={"title": title, "start": start, "end": end}).status_code
            == 201
        )
    with Session(setup_app[0].state.assistant.engine) as db:
        db.add(
            MoodleEvent(
                id="moodle-fixture",
                payload=json.dumps(
                    {
                        "id": "moodle-fixture",
                        "source": "moodle",
                        "title": "Moodle fixture",
                        "start": "2026-10-30",
                        "end": "2026-10-31",
                        "all_day": True,
                        "created_at": "2026-10-29T00:00:00Z",
                    }
                ),
            )
        )
        db.commit()
    assert not any(
        item["kind"] == "upcoming_event" for item in client.get("/notifications").json()["items"]
    )
    response = client.put("/notifications/preferences", json={"events": True})
    assert response.status_code == 200
    items = [item for item in response.json()["items"] if item["kind"] == "upcoming_event"]
    assert {item["title"] for item in items} == {"Meeting fixture", "Moodle fixture"}
    moodle = next(item for item in items if item["title"] == "Moodle fixture")
    assert moodle["start"] == "2026-10-30" and "end" not in moodle
    original = next(item["id"] for item in items if item["title"] == "Meeting fixture")
    assert (
        client.put(
            f"/events/{event['id']}",
            json={
                **event,
                "start": "2026-10-29T15:00:00+02:00",
                "end": "2026-10-29T16:00:00+02:00",
            },
        ).status_code
        == 200
    )
    changed = [
        item
        for item in client.get("/notifications").json()["items"]
        if item["kind"] == "upcoming_event"
    ]
    assert original not in {item["id"] for item in changed}
