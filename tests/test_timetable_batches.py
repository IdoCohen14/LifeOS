import pytest
from test_academic import course_fixture


def preview(client, course, **changes):
    return client.post(
        "/academic/timetable-batches/preview",
        json={
            "course_id": course["id"],
            "weekdays": [0, 2],
            "start_time": "09:00",
            "end_time": "11:00",
            "timezone": "Asia/Jerusalem",
            "location": "Room fixture",
            **changes,
        },
    )


def test_reviewed_weekdays_are_atomic_and_idempotent(client):
    _, course = course_fixture(client)
    result = preview(client, course)
    assert result.status_code == 200
    proposal = result.json()
    assert len(proposal["rows"]) == 2
    assert client.get("/academic/timetable").json() == []
    assert client.post(f"/academic/course-batches/{proposal['id']}/confirm").status_code == 404
    result = client.post(f"/academic/timetable-batches/{proposal['id']}/confirm")
    assert result.status_code == 200 and result.json()["created_count"] == 2
    assert (
        client.post(f"/academic/timetable-batches/{proposal['id']}/confirm").json() == result.json()
    )
    assert sorted(slot["weekday"] for slot in client.get("/academic/timetable").json()) == [0, 2]
    assert preview(client, course).status_code == 409


@pytest.mark.parametrize("weekdays", [[], [0, 0], [True], [-1], [7]])
def test_weekday_selection_is_strict_and_bounded(client, weekdays):
    _, course = course_fixture(client)
    assert preview(client, course, weekdays=weekdays).status_code == 422
    assert client.get("/academic/timetable").json() == []


@pytest.mark.parametrize("change", ["course", "term", "duplicate", "cancel", "cross_kind"])
def test_weekday_approval_protects_changed_sources_and_receipt_kind(client, change):
    term, course = course_fixture(client)
    proposal = preview(client, course).json()
    expected = 409
    if change == "course":
        client.put(f"/academic/courses/{course['id']}", json={**course, "name": "Renamed fixture"})
    elif change == "term":
        client.put(f"/academic/terms/{term['id']}", json={**term, "name": "Renamed term fixture"})
    elif change == "duplicate":
        client.post(
            "/academic/timetable",
            json={
                "course_id": course["id"],
                "weekday": 2,
                "start_time": "09:00",
                "end_time": "11:00",
                "timezone": "Asia/Jerusalem",
            },
        )
    elif change == "cancel":
        assert client.delete(f"/academic/timetable-batches/{proposal['id']}").status_code == 204
        expected = 404
    else:
        proposal = client.post(
            "/academic/course-batches/preview",
            json={"term_id": term["id"], "rows": [{"name": "Other fixture"}]},
        ).json()
        expected = 404
    assert (
        client.post(f"/academic/timetable-batches/{proposal['id']}/confirm").status_code == expected
    )
    assert not any(slot["weekday"] == 0 for slot in client.get("/academic/timetable").json())


@pytest.mark.parametrize("change", ["session", "expiry", "after_insert"])
def test_weekday_receipt_and_final_expiry_rollback(client, setup_app, monkeypatch, change):
    import time

    from lifeos import timetable_batches
    from lifeos.course_batches import CourseBatch
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    _, course = course_fixture(client)
    proposal = preview(client, course).json()
    engine = setup_app[0].state.assistant.engine
    expected = 404
    later = time.time() + 901

    def expire(conn, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith("INSERT INTO TIMETABLE"):
            monkeypatch.setattr(timetable_batches.time, "time", lambda: later)

    if change == "session":
        response = client.post("/session", json={"password": "correct horse battery staple"})
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
    elif change == "expiry":
        with Session(engine) as db:
            db.get(CourseBatch, proposal["id"]).expires = 0
            db.commit()
    else:
        expected = 409
        event.listen(engine, "after_cursor_execute", expire)
    try:
        assert (
            client.post(f"/academic/timetable-batches/{proposal['id']}/confirm").status_code
            == expected
        )
    finally:
        if change == "after_insert":
            event.remove(engine, "after_cursor_execute", expire)
    assert client.get("/academic/timetable").json() == []
