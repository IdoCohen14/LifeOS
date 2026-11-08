from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import event
from test_academic import course_fixture


@pytest.mark.parametrize("operation", ["create", "update"])
def test_concurrent_grade_validation_cannot_commit_weights_above_100(client, setup_app, operation):
    _, course = course_fixture(client)
    existing = []
    if operation == "update":
        for title in ["First concurrent fixture", "Second concurrent fixture"]:
            response = client.post(
                "/academic/grades",
                json={"course_id": course["id"], "title": title, "score": 90, "weight": 10},
            )
            assert response.status_code == 201
            existing.append(response.json()["id"])
    engine = setup_app[0].state.assistant.engine
    first_read, release, second_attempt, second_done = (Event() for _ in range(4))
    first_connection = []
    second_mode = []

    def grade_query(statement):
        return "from grades" in " ".join(statement.lower().split())

    def before(conn, cursor, statement, parameters, context, many):
        if first_connection and conn is not first_connection[0] and not second_attempt.is_set():
            if statement.strip().upper() == "BEGIN IMMEDIATE":
                second_mode.append("write_lock")
                second_attempt.set()
            elif grade_query(statement):
                second_mode.append("unlocked_read")
                second_attempt.set()

    def after(conn, cursor, statement, parameters, context, many):
        if grade_query(statement) and not first_connection:
            first_connection.append(conn)
            first_read.set()
            assert release.wait(8), "First validation was not released"

    def save(index, finished=None):
        try:
            return client.request(
                "PUT" if operation == "update" else "POST",
                f"/academic/grades/{existing[index]}" if existing else "/academic/grades",
                json={
                    "course_id": course["id"],
                    "title": f"Concurrent fixture {index}",
                    "score": 90,
                    "weight": 60,
                },
            ).status_code
        finally:
            if finished:
                finished.set()

    event.listen(engine, "before_cursor_execute", before)
    event.listen(engine, "after_cursor_execute", after)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(save, 0)
            try:
                assert first_read.wait(3)
                second = pool.submit(save, 1, second_done)
                assert second_attempt.wait(3)
                # For an unlocked read, finish its commit before releasing the old snapshot.
                # A serialized writer must instead be released at its lock attempt.
                if second_mode == ["unlocked_read"]:
                    assert second_done.wait(3)
            finally:
                release.set()
            statuses = sorted([first.result(timeout=5), second.result(timeout=5)])
    finally:
        release.set()
        event.remove(engine, "before_cursor_execute", before)
        event.remove(engine, "after_cursor_execute", after)
    assert statuses == [200 if operation == "update" else 201, 422]
    grades = client.get("/academic/grades").json()
    assert len(grades) == (2 if operation == "update" else 1)
    assert sum(grade["weight"] for grade in grades) == (70 if operation == "update" else 60)


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
def test_busy_academic_write_is_retryable_without_partial_changes(client, setup_app, operation):
    _, course = course_fixture(client)
    body = {"course_id": course["id"], "title": "Busy grade fixture", "score": 90, "weight": 10}
    original = client.post("/academic/grades", json=body).json()
    engine = setup_app[0].state.assistant.engine

    def short_fixture_timeout(connection, record, proxy):
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout=50")
        finally:
            cursor.close()

    def attempt():
        if operation == "delete":
            return client.delete(f"/academic/grades/{original['id']}")
        return client.request(
            "PUT" if operation == "update" else "POST",
            f"/academic/grades/{original['id']}" if operation == "update" else "/academic/grades",
            json={**body, "weight": 60},
        )

    event.listen(engine, "checkout", short_fixture_timeout)
    try:
        with engine.connect() as writer:
            writer.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                response = attempt()
                assert response.status_code == 503
                assert response.json()["detail"] == "academic_busy"
                assert response.headers["Retry-After"] == "1"
                assert client.get("/academic/grades").json() == [original]
            finally:
                writer.rollback()
        retry = attempt()
        assert retry.status_code == {"create": 201, "update": 200, "delete": 204}[operation]
        grades = client.get("/academic/grades").json()
        assert len(grades) == {"create": 2, "update": 1, "delete": 0}[operation]
    finally:
        event.remove(engine, "checkout", short_fixture_timeout)
