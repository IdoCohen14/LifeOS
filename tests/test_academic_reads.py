import pytest
from test_academic import course_fixture


def test_academic_listing_never_returns_a_truncated_success(client, setup_app, monkeypatch):
    from lifeos import academic_reads
    from lifeos.academic_models import Term
    from sqlalchemy.orm import Session

    monkeypatch.setattr(academic_reads, "MAX_RECORDS", 2)
    with Session(setup_app[0].state.assistant.engine) as db:
        db.add_all(
            [
                Term(id=str(i), name=f"Fixture {i}", start_date="2026-10-01", end_date="2027-01-01")
                for i in range(2)
            ]
        )
        db.commit()
    assert len(client.get("/academic/terms").json()) == 2
    with Session(setup_app[0].state.assistant.engine) as db:
        db.add(
            Term(
                id="extra", name="Overflow fixture", start_date="2026-10-01", end_date="2027-01-01"
            )
        )
        db.commit()
    response = client.get("/academic/terms")
    assert response.status_code == 503
    assert response.json() == {"detail": "academic_resource_limit"}


def test_academic_calendar_caps_expansion_and_retains_complete_results(client, monkeypatch):
    from lifeos import academic_reads

    _, course = course_fixture(client)
    response = client.post(
        "/academic/timetable",
        json={
            "course_id": course["id"],
            "weekday": 0,
            "start_time": "09:00",
            "end_time": "10:00",
            "timezone": "Asia/Jerusalem",
        },
    )
    assert response.status_code == 201
    original = client.get("/academic/calendar").json()
    assert len(original) > 2
    monkeypatch.setattr(academic_reads, "MAX_RECORDS", len(original))
    assert client.get("/academic/calendar").json() == original
    monkeypatch.setattr(academic_reads, "MAX_RECORDS", len(original) - 1)
    assert client.get("/academic/calendar").status_code == 503


@pytest.mark.parametrize("limit", ["work", "time"])
def test_academic_reads_check_cooperative_limits_even_for_empty_results(client, monkeypatch, limit):
    from lifeos import academic_reads

    if limit == "work":
        monkeypatch.setattr(academic_reads, "MAX_STEPS", 0)
    else:
        monkeypatch.setattr(academic_reads, "MAX_SECONDS", 0)
    for path in ["terms", "courses", "items", "timetable", "grades", "calendar"]:
        assert client.get(f"/academic/{path}").status_code == 503


def test_completed_only_calendar_still_checks_source_work(client, monkeypatch):
    from lifeos import academic_reads

    _, course = course_fixture(client)
    for index in range(3):
        assert (
            client.post(
                "/academic/items",
                json={
                    "course_id": course["id"],
                    "title": f"Completed fixture {index}",
                    "kind": "assignment",
                    "due": "2026-11-02",
                    "completed": True,
                },
            ).status_code
            == 201
        )
    assert client.get("/academic/calendar").json() == []
    monkeypatch.setattr(academic_reads, "MAX_STEPS", 3)
    response = client.get("/academic/calendar")
    assert response.status_code == 503
    assert response.json()["detail"] == "academic_resource_limit"


def test_elapsed_deadline_during_iteration_rejects_entire_list(monkeypatch):
    from fastapi import HTTPException
    from lifeos import academic_reads

    clock = [0.0]
    monkeypatch.setattr(academic_reads.time, "monotonic", lambda: clock[0])
    budget = academic_reads.ReadBudget()

    def rows():
        yield "first fixture"
        clock[0] = academic_reads.MAX_SECONDS
        yield "second fixture"

    with pytest.raises(HTTPException) as failure:
        budget.collect(rows())
    assert failure.value.status_code == 503
