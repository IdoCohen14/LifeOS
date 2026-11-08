from datetime import datetime, timezone

from test_academic import course_fixture


def test_academic_review_reports_entered_effort_without_inventing_missing_estimates(
    client, monkeypatch
):
    from lifeos import academic_review

    monkeypatch.setattr(
        academic_review, "current_time", lambda: datetime(2026, 10, 26, 10, tzinfo=timezone.utc)
    )
    _, course = course_fixture(client)
    for title, hours, completed in [
        ("Known fixture", 2.5, False),
        ("Unknown fixture", 0, False),
        ("Completed fixture", 4, True),
    ]:
        assert (
            client.post(
                "/academic/items",
                json={
                    "course_id": course["id"],
                    "title": title,
                    "kind": "assignment",
                    "due": "2026-10-27",
                    "effort_hours": hours,
                    "completed": completed,
                },
            ).status_code
            == 201
        )
    result = client.get("/review/academic").json()
    assert result["assignments_total"] == 2
    assert result["known_effort_hours"] == 2.5
    assert result["unestimated_assignments"] == 1
    assert {row["title"] for row in result["upcoming_assignments"]} == {
        "Known fixture",
        "Unknown fixture",
    }
