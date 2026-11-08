from datetime import datetime, timezone
from types import SimpleNamespace

import pytest


def fixture_events(client, monkeypatch):
    from lifeos import recommendations

    monkeypatch.setattr(
        recommendations, "current_time", lambda: datetime(2026, 10, 27, 8, tzinfo=timezone.utc)
    )
    for index in range(3):
        assert (
            client.post(
                "/events",
                json={
                    "title": f"Source budget fixture {index}",
                    "notes": "Private fixture notes",
                    "start": "2026-10-27T10:00:00Z",
                    "end": "2026-10-27T11:00:00Z",
                },
            ).status_code
            == 201
        )


@pytest.mark.parametrize("guard", ["count", "deadline"])
def test_production_recommendation_calendar_stops_at_source_budget(client, monkeypatch, guard):
    from lifeos import briefings

    fixture_events(client, monkeypatch)
    if guard == "count":
        monkeypatch.setattr(briefings, "MAX_EVENTS", 2)
    else:
        monkeypatch.setattr(briefings, "time", SimpleNamespace(monotonic=lambda: float("inf")))
    response = client.get("/recommendations")
    assert response.status_code == 503
    assert response.json() == {"detail": "recommendation_resource_limit"}


def test_recommendation_calendar_excludes_notes_and_never_uses_materializing_provider_methods(
    client, setup_app, monkeypatch
):
    from sqlalchemy import event

    fixture_events(client, monkeypatch)
    app = setup_app[0]
    for provider in (app.state.google, app.state.moodle):
        monkeypatch.setattr(
            provider, "events", lambda: pytest.fail("Materializing provider method called")
        )
        monkeypatch.setattr(provider, "sync", lambda: pytest.fail("No provider sync"))
    queries = []

    def observed(connection, cursor, statement, parameters, context, many):
        if statement.startswith("SELECT") and "FROM events" in statement:
            queries.append(statement)

    engine = app.state.assistant.engine
    event.listen(engine, "before_cursor_execute", observed)
    try:
        response = client.get("/recommendations")
    finally:
        event.remove(engine, "before_cursor_execute", observed)
    assert response.status_code == 200 and len(response.json()["items"]) == 3
    assert queries and all(
        "events.notes" not in query and "events.created_at" not in query for query in queries
    )


def test_cached_iterator_matches_actual_mixed_sources_and_exact_limit(
    client, setup_app, monkeypatch
):
    import json
    import time

    from lifeos import briefings
    from lifeos.academic_models import Course, Term, TimetableSlot
    from lifeos.google_models import GoogleCalendar, GoogleRecord
    from lifeos.moodle_models import MoodleEvent
    from lifeos.recommendations import RecommendationService
    from sqlalchemy.orm import Session

    fixture_events(client, monkeypatch)
    app = setup_app[0]
    engine = app.state.assistant.engine
    personal = client.get("/events").json()[0]
    with Session(engine) as db:
        db.add(Term(id="term", name="Term fixture", start_date="2026-10-27", end_date="2026-10-27"))
        db.flush()
        db.add(Course(id="course", term_id="term", name="Course fixture"))
        db.flush()
        db.add(
            TimetableSlot(
                id="slot",
                course_id="course",
                weekday=2,
                start_time="12:00",
                end_time="13:00",
                timezone="Asia/Jerusalem",
            )
        )
        db.add_all(
            [
                GoogleCalendar(
                    id="selected", name="Selected fixture", timezone="Asia/Jerusalem", selected=True
                ),
                GoogleCalendar(
                    id="hidden", name="Hidden fixture", timezone="Asia/Jerusalem", selected=False
                ),
            ]
        )
        db.flush()
        db.add_all(
            [
                GoogleRecord(
                    calendar_id="selected",
                    external_id="mirror",
                    kind="visible",
                    payload=json.dumps({**personal, "id": "mirror", "source": "google"}),
                ),
                GoogleRecord(
                    calendar_id="hidden",
                    external_id="hidden",
                    kind="visible",
                    payload=json.dumps(
                        {**personal, "id": "hidden", "title": "Hidden fixture", "source": "google"}
                    ),
                ),
            ]
        )
        db.add(
            MoodleEvent(
                id="moodle",
                payload=json.dumps(
                    {**personal, "id": "moodle", "title": "Moodle fixture", "source": "moodle"}
                ),
            )
        )
        db.commit()

    # Independent legacy source composition: assistant.calendar now uses the bounded helper too.
    def legacy_calendar():
        from lifeos.academic_calendar import project_calendar
        from lifeos.models import CalendarEvent
        from sqlalchemy import select

        with Session(engine) as db:
            personal = [
                {
                    "id": row.id,
                    "title": row.title,
                    "start": row.start,
                    "end": row.end,
                    "all_day": row.all_day,
                    "source": "personal",
                }
                for row in db.scalars(select(CalendarEvent))
            ]
            academic = project_calendar(db)
        return personal + academic + app.state.google.events() + app.state.moodle.events()

    legacy = RecommendationService(engine, legacy_calendar, app.state.google, app.state.moodle)
    expected = legacy.candidates()
    assert app.state.recommendations.candidates() == expected
    assert len(expected[0]) == 10
    with Session(engine) as db:
        deadline = time.monotonic() + 10
        monkeypatch.setattr(briefings, "MAX_EVENTS", 6)
        records = list(briefings.iter_cached_calendar(db, deadline, include_titles=True))
        assert len(records) == 6 and {row["source"] for row in records} == {
            "personal",
            "timetable",
            "google",
            "moodle",
        }
        assert not any(row["id"] == "hidden" for row in records)
        assert briefings.cached_calendar(db, deadline, include_titles=True) == records
        monkeypatch.setattr(briefings, "MAX_EVENTS", 5)
        with pytest.raises(briefings.BriefingProblem, match="briefing_resource_limit"):
            briefings.cached_calendar(db, deadline)


def test_cached_iterator_does_not_query_after_preexpired_deadline(client, setup_app, monkeypatch):
    import time

    from lifeos import briefings
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    engine = setup_app[0].state.assistant.engine
    queries = []

    def observed(connection, cursor, statement, parameters, context, many):
        queries.append(statement)

    event.listen(engine, "before_cursor_execute", observed)
    try:
        with Session(engine) as db, pytest.raises(briefings.BriefingProblem):
            list(briefings.iter_cached_calendar(db, time.monotonic() - 1))
    finally:
        event.remove(engine, "before_cursor_execute", observed)
    assert queries == []


def test_owned_calendar_session_closes_even_with_retained_consumer_exception(
    client, setup_app, monkeypatch
):
    from lifeos import briefings

    engine = setup_app[0].state.assistant.engine

    def invalid_source(*args, **kwargs):
        yield {
            "id": "bad-fixture",
            "title": "Invalid fixture",
            "start": "invalid",
            "end": "2026-10-27T11:00:00Z",
            "all_day": False,
            "source": "personal",
        }

    monkeypatch.setattr(briefings, "iter_cached_calendar", invalid_source)
    before = engine.pool.checkedout()
    with pytest.raises(ValueError) as retained:
        setup_app[0].state.recommendations.candidates()
    assert retained.value.__traceback__ is not None
    assert engine.pool.checkedout() == before
