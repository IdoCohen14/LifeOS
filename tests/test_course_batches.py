import pytest
from test_academic import course_fixture


def preview(client, term, **changes):
    return client.post(
        "/academic/course-batches/preview",
        json={
            "term_id": term["id"],
            "rows": [
                {"name": "Batch algebra", "code": "MAT1", "credits": 4},
                {"name": "Batch physics", "code": "PHY1"},
            ],
            **changes,
        },
    )


def test_batch_review_then_atomic_confirm_and_retry(client):
    term, existing = course_fixture(client)
    response = preview(client, term)
    assert response.status_code == 200
    proposal = response.json()
    assert len(proposal["rows"]) == 2 and proposal["term"]["name"] == term["name"]
    assert client.get("/academic/courses").json() == [existing]
    result = client.post(f"/academic/course-batches/{proposal['id']}/confirm")
    assert result.status_code == 200 and result.json()["created_count"] == 2
    assert client.post(f"/academic/course-batches/{proposal['id']}/confirm").json() == result.json()
    assert len(client.get("/academic/courses").json()) == 3


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [{"name": "Same"}, {"name": " same "}],
        [{"name": "A", "code": "X"}, {"name": "B", "code": "x"}],
        [{"name": "X"}] * 21,
        [{"name": "Bad", "unknown": 1}],
    ],
)
def test_batch_invalid_rows_do_not_create_courses(client, rows):
    term, existing = course_fixture(client)
    assert preview(client, term, rows=rows).status_code == 422
    assert client.get("/academic/courses").json() == [existing]


@pytest.mark.parametrize("change", ["term", "duplicate", "cancel", "session", "expiry"])
def test_batch_approval_revalidates_and_never_partially_creates(client, setup_app, change):
    from lifeos.course_batches import CourseBatch
    from sqlalchemy.orm import Session

    term, existing = course_fixture(client)
    proposal = preview(client, term).json()
    expected = 409
    if change == "term":
        assert (
            client.put(
                f"/academic/terms/{term['id']}", json={**term, "name": "Changed term"}
            ).status_code
            == 200
        )
    elif change == "duplicate":
        assert (
            client.post(
                "/academic/courses", json={"term_id": term["id"], "name": "Batch physics"}
            ).status_code
            == 201
        )
    elif change == "cancel":
        assert client.delete(f"/academic/course-batches/{proposal['id']}").status_code == 204
        expected = 404
    elif change == "session":
        result = client.post("/session", json={"password": "correct horse battery staple"})
        client.headers["X-CSRF-Token"] = result.json()["csrf"]
        expected = 404
    else:
        with Session(setup_app[0].state.assistant.engine) as db:
            db.get(CourseBatch, proposal["id"]).expires = 0
            db.commit()
        expected = 404
    assert client.post(f"/academic/course-batches/{proposal['id']}/confirm").status_code == expected
    courses = client.get("/academic/courses").json()
    assert not any(course["name"] == "Batch algebra" for course in courses)


def test_batch_expiry_after_inserts_rolls_back_every_course(client, setup_app, monkeypatch):
    import time

    from lifeos import course_batches
    from sqlalchemy import event

    term, existing = course_fixture(client)
    proposal = preview(client, term).json()
    engine = setup_app[0].state.assistant.engine
    later = time.time() + 901

    def expire(conn, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith("INSERT INTO COURSES"):
            monkeypatch.setattr(course_batches.time, "time", lambda: later)

    event.listen(engine, "after_cursor_execute", expire)
    try:
        response = client.post(f"/academic/course-batches/{proposal['id']}/confirm")
        assert response.status_code == 409
    finally:
        event.remove(engine, "after_cursor_execute", expire)
    assert client.get("/academic/courses").json() == [existing]
