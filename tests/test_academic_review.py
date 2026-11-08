from datetime import datetime, timezone

from test_academic import course_fixture


def test_academic_snapshot_uses_entered_weights_and_upcoming_actual_exams(client, monkeypatch):
    from lifeos import academic_review

    monkeypatch.setattr(
        academic_review, "current_time", lambda: datetime(2026, 10, 26, 10, tzinfo=timezone.utc)
    )
    _, course = course_fixture(client)
    for index, (score, maximum, weight) in enumerate(
        [(90, 100, 60), (40, 50, 30), (100, 100, None)]
    ):
        assert (
            client.post(
                "/academic/grades",
                json={
                    "course_id": course["id"],
                    "title": f"Grade fixture {index}",
                    "score": score,
                    "maximum": maximum,
                    "weight": weight,
                },
            ).status_code
            == 201
        )
    for kind, due, completed in [
        ("exam", "2026-10-27", False),
        ("exam", "2026-10-25", False),
        ("exam", "2026-10-27", True),
        ("assignment", "2026-10-27", False),
    ]:
        assert (
            client.post(
                "/academic/items",
                json={
                    "course_id": course["id"],
                    "title": "Academic fixture",
                    "kind": kind,
                    "due": due,
                    "completed": completed,
                },
            ).status_code
            == 201
        )
    before = client.get("/tasks").json()
    response = client.get("/review/academic")
    assert response.status_code == 200
    body = response.json()
    assert body["range_start"] == "2026-10-26" and body["range_end"] == "2026-11-02"
    assert body["grades"][0]["grade_count"] == 3
    assert body["grades"][0]["known_weight"] == 90
    assert body["grades"][0]["weighted_percent"] == 86.67
    assert body["exams_total"] == 1 and body["upcoming_exams"][0]["due"] == "2026-10-27"
    assert client.get("/tasks").json() == before
