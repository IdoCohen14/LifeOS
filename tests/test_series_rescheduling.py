from datetime import datetime, timedelta, timezone

import pytest


def prepared(client, monkeypatch, **overrides):
    from lifeos import recurring_events, series_management

    now = overrides.pop("_now", datetime(2026, 10, 27, 6, tzinfo=timezone.utc))
    monkeypatch.setattr(recurring_events, "current_time", lambda: now)
    monkeypatch.setattr(series_management, "current_time", lambda: now)
    import sys

    module = sys.modules.get("lifeos.series_rescheduling")
    if module:
        monkeypatch.setattr(module, "current_time", lambda: now)
    if "timezone" in overrides:
        assert client.put("/settings", json={"timezone": overrides["timezone"]}).status_code == 200
    response = client.post(
        "/recurrence/preview",
        json={
            "title": "Clock change fixture",
            "notes": "Retain fixture notes",
            "day": "2026-10-28",
            "clock": "09:00",
            "duration": 60,
            "count": 3,
            "timezone": "Asia/Jerusalem",
            **overrides,
        },
    )
    assert response.status_code == 200
    saved = client.post("/recurrence/confirm", json={"id": response.json()["id"]}).json()
    return saved["series_id"]


def proposal(client, series, **overrides):
    return client.post(
        f"/recurrence/series/{series}/reschedule-preview",
        json={
            "from_day": "2026-10-27",
            "clock": "11:00",
            "duration": 45,
            **overrides,
        },
    )


def date_shift(client, series, days=1, **overrides):
    return client.post(
        f"/recurrence/series/{series}/reschedule-preview",
        json={"from_day": "2026-10-27", "day_shift": days, "preserve_time": True, **overrides},
    )


def test_series_date_shift_preserves_clocks_duration_precision_and_edited_protection(
    client, monkeypatch
):
    from zoneinfo import ZoneInfo

    series = prepared(client, monkeypatch)
    events = client.get("/events").json()
    edited = client.put(
        "/events/" + events[1]["id"],
        json={
            **events[1],
            "title": "Protected precision fixture",
            "start": "2026-11-04T11:17:23.125+02:00",
            "end": "2026-11-04T14:22:24.250+02:00",
        },
    ).json()
    response = date_shift(client, series, 2)
    assert response.status_code == 200
    plan = response.json()
    assert len(plan["events"]) == 2 and plan["skipped_modified"] == 1
    assert client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).json() == {
        "changed_count": 2
    }
    assert next(row for row in client.get("/events").json() if row["id"] == edited["id"]) == edited
    before = {row["id"]: row for row in client.get("/events").json()}
    included = date_shift(client, series, 1, include_modified=True).json()
    assert len(included["events"]) == 3
    assert client.post("/recurrence/reschedules/confirm", json={"id": included["id"]}).json() == {
        "changed_count": 3
    }
    for row in client.get("/events").json():
        old = before[row["id"]]
        start = datetime.fromisoformat(row["start"].replace("Z", "+00:00"))
        old_start = datetime.fromisoformat(old["start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(row["end"].replace("Z", "+00:00"))
        old_end = datetime.fromisoformat(old["end"].replace("Z", "+00:00"))
        assert (
            start.astimezone(ZoneInfo("Asia/Jerusalem")).time()
            == old_start.astimezone(ZoneInfo("Asia/Jerusalem")).time()
        )
        assert end - start == old_end - old_start
        assert {key: value for key, value in row.items() if key not in ("start", "end")} == {
            key: value for key, value in old.items() if key not in ("start", "end")
        }
    next_plan = date_shift(client, series, 1).json()
    assert next_plan["skipped_modified"] == 1
    assert client.post("/recurrence/reschedules/confirm", json={"id": included["id"]}).json() == {
        "changed_count": 3
    }


def test_reschedule_preview_protects_edits_and_updates_only_reviewed_fields(client, monkeypatch):
    series = prepared(client, monkeypatch)
    events = client.get("/events").json()
    edited = client.put(
        "/events/" + events[1]["id"], json={**events[1], "title": "Edited fixture"}
    ).json()
    before = client.get("/events").json()
    response = proposal(client, series)
    assert response.status_code == 200
    plan = response.json()
    assert len(plan["events"]) == 2 and plan["skipped_modified"] == 1
    assert client.get("/events").json() == before
    assert all(row["start"] != row["new_start"] for row in plan["events"])
    result = client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]})
    assert result.status_code == 200 and result.json() == {"changed_count": 2}
    after = {row["id"]: row for row in client.get("/events").json()}
    assert after[edited["id"]] == edited
    for row in plan["events"]:
        source = next(value for value in before if value["id"] == row["id"])
        assert after[row["id"]] == {**source, "start": row["new_start"], "end": row["new_end"]}
    assert (
        client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).json()
        == result.json()
    )
    second = proposal(client, series, clock="12:00").json()
    assert len(second["events"]) == 2 and second["skipped_modified"] == 1
    included = proposal(client, series, clock="12:00", include_modified=True).json()
    assert client.post("/recurrence/reschedules/confirm", json={"id": included["id"]}).json() == {
        "changed_count": 3
    }
    subsequent = proposal(client, series, clock="13:00").json()
    assert len(subsequent["events"]) == 2 and subsequent["skipped_modified"] == 1
    assert (
        next(row for row in client.get("/events").json() if row["id"] == edited["id"])["title"]
        == edited["title"]
    )


def test_reschedule_stale_source_cancel_and_noop(client, monkeypatch):
    series = prepared(client, monkeypatch)
    noop = proposal(client, series, clock="09:00", duration=60).json()
    assert noop["id"] is None and noop["events"] == [] and noop["skipped_unchanged"] == 3
    plan = proposal(client, series).json()
    event = client.get("/events").json()[0]
    client.put("/events/" + event["id"], json={**event, "notes": "Changed fixture"})
    before = client.get("/events").json()
    assert (
        client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).status_code == 409
    )
    assert client.get("/events").json() == before
    assert client.delete("/recurrence/reschedules/" + plan["id"]).status_code == 204
    assert (
        client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).status_code == 404
    )


def test_reschedule_all_day_and_dst_reject_entire_preview(client, monkeypatch):
    series = prepared(client, monkeypatch, all_day=True)
    plan = proposal(client, series).json()
    assert plan["id"] is None and plan["skipped_all_day"] == 3
    timed = prepared(client, monkeypatch, day="2026-10-30", count=23)
    before = client.get("/events").json()
    response = proposal(client, timed, clock="02:30")
    assert response.status_code == 422 and response.json()["detail"] == "series_time_ambiguous"
    assert client.get("/events").json() == before


@pytest.mark.parametrize("all_day,renaming", [(False, False), (True, False), (True, True)])
def test_reschedule_postflush_budget_rolls_back_sources_and_baselines(
    client, setup_app, monkeypatch, all_day, renaming
):
    from fastapi import HTTPException
    from lifeos import series_rescheduling
    from lifeos.series_models import SeriesOccurrence
    from sqlalchemy import event, select
    from sqlalchemy.orm import Session

    series = prepared(client, monkeypatch, all_day=all_day)
    plan = (
        rename(client, series)
        if renaming
        else (
            date_shift(client, series, include_all_day=True)
            if all_day
            else proposal(client, series)
        )
    ).json()
    engine = setup_app[0].state.assistant.engine
    before = client.get("/events").json()
    with Session(engine) as db:
        baselines = {
            row.event_id: row.original_signature for row in db.scalars(select(SeriesOccurrence))
        }
    flushed = []

    def observed(connection, cursor, statement, parameters, context, many):
        if statement.startswith("UPDATE events"):
            flushed.append(True)

    original = series_rescheduling.budget

    def expired(deadline):
        if flushed:
            raise HTTPException(503, "series_resource_limit")
        original(deadline)

    event.listen(engine, "after_cursor_execute", observed)
    monkeypatch.setattr(series_rescheduling, "budget", expired)
    try:
        assert (
            client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).status_code
            == 503
        )
    finally:
        event.remove(engine, "after_cursor_execute", observed)
    assert flushed and client.get("/events").json() == before
    with Session(engine) as db:
        assert {
            row.event_id: row.original_signature for row in db.scalars(select(SeriesOccurrence))
        } == baselines
    monkeypatch.setattr(series_rescheduling, "budget", original)
    assert client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).json() == {
        "changed_count": 3
    }


def test_reschedule_baseline_change_unknown_protection_and_final_time_fence(
    client, setup_app, monkeypatch
):
    from lifeos import series_rescheduling
    from lifeos.series_models import SeriesOccurrence
    from sqlalchemy import event, select
    from sqlalchemy.orm import Session

    series = prepared(client, monkeypatch)
    plan = proposal(client, series).json()
    engine = setup_app[0].state.assistant.engine
    with Session(engine) as db:
        link = db.scalar(select(SeriesOccurrence).where(SeriesOccurrence.series_id == series))
        link.original_signature = None
        db.commit()
    assert (
        client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).status_code == 409
    )
    protected = proposal(client, series).json()
    assert len(protected["events"]) == 2 and protected["skipped_modified"] == 1
    included = proposal(client, series, include_modified=True, from_day="2026-10-28").json()
    assert len(included["events"]) == 3 and sum(row["unknown"] for row in included["events"]) == 1
    before = client.get("/events").json()

    def crossed(connection, cursor, statement, parameters, context, many):
        if statement.startswith("UPDATE events"):
            monkeypatch.setattr(
                series_rescheduling,
                "current_time",
                lambda: datetime(2026, 10, 28, 7, tzinfo=timezone.utc),
            )

    event.listen(engine, "after_cursor_execute", crossed)
    try:
        assert (
            client.post("/recurrence/reschedules/confirm", json={"id": included["id"]}).status_code
            == 409
        )
    finally:
        event.remove(engine, "after_cursor_execute", crossed)
    assert client.get("/events").json() == before


def test_reschedule_session_expiry_limits_validation_and_original_zone(
    client, setup_app, monkeypatch
):
    from lifeos.series_models import SeriesRescheduleProposal
    from sqlalchemy.orm import Session

    series = prepared(client, monkeypatch)
    for values in (
        {"from_day": "2026-10-26"},
        {"from_day": "2028-01-01"},
        {"clock": "25:00"},
        {"duration": 6},
        {"duration": True},
    ):
        assert proposal(client, series, **values).status_code == 422
    plan = proposal(client, series).json()
    token = client.headers.pop("X-CSRF-Token")
    assert (
        client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).status_code == 403
    )
    client.headers["X-CSRF-Token"] = token
    with Session(setup_app[0].state.assistant.engine) as db:
        db.get(SeriesRescheduleProposal, plan["id"]).expires = 0
        db.commit()
    assert (
        client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).status_code == 404
    )
    for _ in range(20):
        assert proposal(client, series).status_code == 200
    assert proposal(client, series).status_code == 429
    session = client.post("/session", json={"password": "correct horse battery staple"}).json()
    client.headers["X-CSRF-Token"] = session["csrf"]
    assert (
        client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).status_code == 404
    )
    client.put("/settings", json={"timezone": "America/New_York"})
    next_plan = proposal(client, series).json()
    assert next_plan["timezone"] == "Asia/Jerusalem"
    assert client.post("/recurrence/reschedules/confirm", json={"id": next_plan["id"]}).json() == {
        "changed_count": 3
    }


def test_reschedule_populated_migration_preserves_sources_and_links(client, setup_app, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from lifeos.db import ROOT, migrate
    from sqlalchemy import text

    series = prepared(client, monkeypatch)
    before = client.get("/events").json()
    engine = setup_app[0].state.assistant.engine
    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "services/api/alembic"))
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.downgrade(cfg, "0019")
    migrate(engine)
    assert client.get("/events").json() == before
    assert client.get("/recurrence/series").json()["items"][0]["count"] == 3
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM series_reschedule_proposals")) == 0
    assert proposal(client, series).status_code == 200


@pytest.mark.parametrize("days", [0, 29, -29, True, 1.5, "1"])
def test_series_date_shift_rejects_invalid_or_mixed_modes(client, monkeypatch, days):
    series = prepared(client, monkeypatch)
    assert date_shift(client, series, days).status_code == 422
    assert date_shift(client, series, 1, clock="09:00", duration=60).status_code == 422
    assert date_shift(client, series, 1, preserve_time=False).status_code == 422
    assert len(client.get("/events").json()) == 3


def test_series_date_shift_negative_past_and_all_day_behavior(client, monkeypatch):
    series = prepared(client, monkeypatch)
    before = client.get("/events").json()
    assert date_shift(client, series, -2).status_code == 422
    assert client.get("/events").json() == before
    selected = date_shift(client, series, -2, from_day="2026-11-04").json()
    assert len(selected["events"]) == 2
    assert client.post("/recurrence/reschedules/confirm", json={"id": selected["id"]}).json() == {
        "changed_count": 2
    }
    assert (
        next(row for row in client.get("/events").json() if row["id"] == before[0]["id"])
        == before[0]
    )
    all_day = prepared(client, monkeypatch, all_day=True)
    empty = date_shift(client, all_day).json()
    assert empty["id"] is None and empty["skipped_all_day"] == 3


@pytest.mark.parametrize("clock,count,days", [("02:30", 23, 1), ("01:30", 52, 10)])
def test_series_date_shift_rejects_missing_or_repeated_destination_time(
    client, monkeypatch, clock, count, days
):
    series = prepared(client, monkeypatch, day="2026-10-29", clock=clock, count=count)
    before = client.get("/events").json()
    response = date_shift(client, series, days)
    assert response.status_code == 422 and response.json()["detail"] == "series_time_ambiguous"
    assert client.get("/events").json() == before


def test_series_date_shift_is_local_days_not_24hour_blocks_across_dst(client, monkeypatch):
    from lifeos import recurring_events, series_rescheduling

    now = datetime(2026, 10, 20, 6, tzinfo=timezone.utc)
    monkeypatch.setattr(recurring_events, "current_time", lambda: now)
    monkeypatch.setattr(series_rescheduling, "current_time", lambda: now)
    created = client.post(
        "/recurrence/preview",
        json={
            "title": "DST day shift fixture",
            "day": "2026-10-23",
            "clock": "09:00",
            "duration": 90,
            "count": 2,
            "timezone": "Asia/Jerusalem",
        },
    ).json()
    saved = client.post("/recurrence/confirm", json={"id": created["id"]}).json()
    before = client.get("/events").json()
    plan = date_shift(client, saved["series_id"], 3, from_day="2026-10-20").json()
    first = plan["events"][0]
    start = datetime.fromisoformat(first["new_start"].replace("Z", "+00:00"))
    old = datetime.fromisoformat(before[0]["start"].replace("Z", "+00:00"))
    assert start - old == timedelta(hours=73)
    assert client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).json() == {
        "changed_count": 2
    }


def test_series_date_shift_postflush_start_crossing_rolls_back(client, setup_app, monkeypatch):
    from lifeos import series_rescheduling
    from sqlalchemy import event

    series = prepared(client, monkeypatch)
    clock = [datetime(2026, 10, 27, 6, 59, 59, tzinfo=timezone.utc)]
    monkeypatch.setattr(series_rescheduling, "current_time", lambda: clock[0])
    plan = date_shift(client, series, -1).json()
    before = client.get("/events").json()
    engine = setup_app[0].state.assistant.engine
    flushed = []

    def crossed(connection, cursor, statement, parameters, context, many):
        if statement.startswith("UPDATE events"):
            flushed.append(True)
            clock[0] = datetime(2026, 10, 27, 7, tzinfo=timezone.utc)

    event.listen(engine, "after_cursor_execute", crossed)
    try:
        assert (
            client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).status_code
            == 409
        )
    finally:
        event.remove(engine, "after_cursor_execute", crossed)
    assert flushed and client.get("/events").json() == before
    clock[0] = datetime(2026, 10, 27, 6, 59, 59, tzinfo=timezone.utc)
    assert client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).json() == {
        "changed_count": 3
    }


def test_series_date_shift_handles_overflow_and_old_clock_preview_payload(
    client, setup_app, monkeypatch
):
    import json

    from lifeos.series_models import SeriesRescheduleProposal
    from sqlalchemy.orm import Session

    series = prepared(client, monkeypatch)
    old = proposal(client, series).json()
    with Session(setup_app[0].state.assistant.engine) as db:
        row = db.get(SeriesRescheduleProposal, old["id"])
        payload = json.loads(row.payload)
        payload.pop("day_shift")
        payload.pop("preserve_time")
        payload.pop("include_all_day")
        payload.pop("new_title")
        payload.pop("target_all_day")
        payload.pop("shift_and_time")
        for item in payload["items"]:
            item.pop("title")
            item.pop("all_day")
        row.payload = json.dumps(payload)
        db.commit()
    assert client.post("/recurrence/reschedules/confirm", json={"id": old["id"]}).json() == {
        "changed_count": 3
    }
    source = client.get("/events").json()[0]
    assert (
        client.put(
            "/events/" + source["id"],
            json={**source, "start": "9999-12-20T09:00:00Z", "end": "9999-12-20T10:00:00Z"},
        ).status_code
        == 200
    )
    before = client.get("/events").json()
    response = date_shift(client, series, 28, include_modified=True)
    assert response.status_code == 422 and response.json()["detail"] == "series_time_invalid"
    assert client.get("/events").json() == before


@pytest.mark.parametrize(
    "day,days",
    [
        ("2026-10-28", -1),
        ("2026-12-31", 1),
        ("2027-02-28", 1),
        ("2027-03-25", 1),
        ("2028-02-28", 1),
    ],
)
def test_all_day_shift_preserves_dates_exclusive_length_and_content(client, monkeypatch, day, days):
    from datetime import date

    reference = datetime.fromisoformat(day).replace(hour=6, tzinfo=timezone.utc) - timedelta(days=1)
    series = prepared(client, monkeypatch, all_day=True, day=day, _now=reference)
    from_day = reference.date().isoformat()
    before = client.get("/events").json()
    default = date_shift(client, series, days, from_day=from_day).json()
    assert default["id"] is None and default["skipped_all_day"] == 3
    response = date_shift(client, series, days, include_all_day=True, from_day=from_day)
    assert response.status_code == 200, response.text
    plan = response.json()
    assert len(plan["events"]) == 3 and plan["skipped_all_day"] == 0
    assert client.get("/events").json() == before
    for row in plan["events"]:
        assert row["all_day"] is True
        assert date.fromisoformat(row["new_start"]) - date.fromisoformat(row["start"]) == timedelta(
            days=days
        )
        assert date.fromisoformat(row["new_end"]) - date.fromisoformat(row["end"]) == timedelta(
            days=days
        )
    assert client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).json() == {
        "changed_count": 3
    }
    after = {row["id"]: row for row in client.get("/events").json()}
    for old in before:
        reviewed = next(row for row in plan["events"] if row["id"] == old["id"])
        assert after[old["id"]] == {
            **old,
            "start": reviewed["new_start"],
            "end": reviewed["new_end"],
        }
    assert (
        date_shift(client, series, 1, include_all_day=True, from_day=from_day).json()[
            "skipped_modified"
        ]
        == 0
    )
    assert client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).json() == {
        "changed_count": 3
    }


def test_all_day_shift_modes_mixed_selection_and_stale_type(client, monkeypatch):
    series = prepared(client, monkeypatch, all_day=True)
    assert proposal(client, series, include_all_day=True).status_code == 422
    assert date_shift(client, series, include_all_day="true").status_code == 422
    rows = client.get("/events").json()
    edited = client.put("/events/" + rows[0]["id"], json={**rows[0], "end": "2026-10-31"}).json()
    timed = client.put(
        "/events/" + rows[1]["id"],
        json={
            **rows[1],
            "all_day": False,
            "start": "2026-11-04T09:00:00+02:00",
            "end": "2026-11-04T10:00:00+02:00",
        },
    ).json()
    protected = date_shift(client, series, 1, include_all_day=True).json()
    assert len(protected["events"]) == 1 and protected["skipped_modified"] == 2
    response = date_shift(client, series, 2, include_all_day=True, include_modified=True)
    assert response.status_code == 200, response.text
    plan = response.json()
    assert len(plan["events"]) == 3 and sum(row["all_day"] for row in plan["events"]) == 2
    reviewed = next(row for row in plan["events"] if row["id"] == edited["id"])
    assert (reviewed["new_start"], reviewed["new_end"]) == ("2026-10-30", "2026-11-02")
    # Changing record type after review must invalidate the entire atomic approval.
    assert (
        client.put(
            "/events/" + timed["id"],
            json={**timed, "all_day": True, "start": "2026-11-04", "end": "2026-11-05"},
        ).status_code
        == 200
    )
    before = client.get("/events").json()
    assert (
        client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).status_code == 409
    )
    assert client.get("/events").json() == before
    current = date_shift(client, series, 2, include_all_day=True, include_modified=True).json()
    assert client.post("/recurrence/reschedules/confirm", json={"id": current["id"]}).json() == {
        "changed_count": 3
    }
    assert date_shift(client, series, 1, include_all_day=True).json()["skipped_modified"] == 1


def test_all_day_shift_rejects_past_overflow_and_midnight_rolls_back(
    client, setup_app, monkeypatch
):
    from lifeos import series_rescheduling
    from sqlalchemy import event

    series = prepared(client, monkeypatch, all_day=True)
    assert date_shift(client, series, -2, include_all_day=True).status_code == 422
    # Destination today is valid even when the local time is already late at night.
    clock = [datetime(2026, 10, 27, 21, 59, 59, tzinfo=timezone.utc)]
    monkeypatch.setattr(series_rescheduling, "current_time", lambda: clock[0])
    response = date_shift(client, series, -1, include_all_day=True)
    assert response.status_code == 200, response.text
    plan = response.json()
    before = client.get("/events").json()
    engine = setup_app[0].state.assistant.engine
    flushed = []

    def crossed(connection, cursor, statement, parameters, context, many):
        if statement.startswith("UPDATE events"):
            flushed.append(True)
            clock[0] = datetime(2026, 10, 27, 22, tzinfo=timezone.utc)

    event.listen(engine, "after_cursor_execute", crossed)
    try:
        assert (
            client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).status_code
            == 409
        )
    finally:
        event.remove(engine, "after_cursor_execute", crossed)
    assert flushed and client.get("/events").json() == before
    clock[0] = datetime(2026, 10, 27, 21, 59, 59, tzinfo=timezone.utc)
    assert client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).json() == {
        "changed_count": 3
    }
    row = client.get("/events").json()[-1]
    assert (
        client.put(
            "/events/" + row["id"], json={**row, "start": "9999-12-20", "end": "9999-12-31"}
        ).status_code
        == 200
    )
    before = client.get("/events").json()
    assert (
        date_shift(client, series, 28, include_all_day=True, include_modified=True).status_code
        == 422
    )
    assert client.get("/events").json() == before


def test_all_day_shift_cancel_expiry_session_zone_and_retry_after_deletion(
    client, setup_app, monkeypatch
):
    from lifeos.series_models import EventSeries, SeriesRescheduleProposal
    from sqlalchemy.orm import Session

    series = prepared(client, monkeypatch, all_day=True)
    engine = setup_app[0].state.assistant.engine

    def make():
        response = date_shift(client, series, include_all_day=True)
        assert response.status_code == 200, response.text
        return response.json()

    cancelled = make()
    assert client.delete("/recurrence/reschedules/" + cancelled["id"]).status_code == 204
    assert (
        client.post("/recurrence/reschedules/confirm", json={"id": cancelled["id"]}).status_code
        == 404
    )
    expired = make()
    with Session(engine) as db:
        db.get(SeriesRescheduleProposal, expired["id"]).expires = 0
        db.commit()
    assert (
        client.post("/recurrence/reschedules/confirm", json={"id": expired["id"]}).status_code
        == 404
    )
    zoned = make()
    with Session(engine) as db:
        db.get(EventSeries, series).timezone = "America/New_York"
        db.commit()
    assert (
        client.post("/recurrence/reschedules/confirm", json={"id": zoned["id"]}).status_code == 409
    )
    owned = make()
    token = client.headers.pop("X-CSRF-Token")
    assert (
        client.post("/recurrence/reschedules/confirm", json={"id": owned["id"]}).status_code == 403
    )
    client.headers["X-CSRF-Token"] = token
    session = client.post("/session", json={"password": "correct horse battery staple"}).json()
    client.headers["X-CSRF-Token"] = session["csrf"]
    assert (
        client.post("/recurrence/reschedules/confirm", json={"id": owned["id"]}).status_code == 404
    )
    plan = make()
    assert client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).json() == {
        "changed_count": 3
    }
    for row in client.get("/events").json():
        assert client.delete("/events/" + row["id"]).status_code == 204
    assert client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).json() == {
        "changed_count": 3
    }


def test_all_day_flag_missing_in_legacy_timed_payload_stays_timed(client, setup_app, monkeypatch):
    import json

    from lifeos.series_models import SeriesRescheduleProposal
    from sqlalchemy.orm import Session

    series = prepared(client, monkeypatch)
    plan = date_shift(client, series).json()
    with Session(setup_app[0].state.assistant.engine) as db:
        row = db.get(SeriesRescheduleProposal, plan["id"])
        payload = json.loads(row.payload)
        payload.pop("include_all_day")
        row.payload = json.dumps(payload)
        db.commit()
    assert client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).json() == {
        "changed_count": 3
    }


def rename(client, series, title="  כותרת חדשה למופעים  ", **overrides):
    return client.post(
        f"/recurrence/series/{series}/reschedule-preview",
        json={"from_day": "2026-10-27", "new_title": title, **overrides},
    )


@pytest.mark.parametrize("all_day", [False, True])
def test_series_titles_change_only_reviewed_titles_and_keep_edited_protection(
    client, monkeypatch, all_day
):
    series = prepared(client, monkeypatch, all_day=all_day)
    rows = client.get("/events").json()
    edited = client.put(
        "/events/" + rows[0]["id"], json={**rows[0], "notes": "Protected title fixture"}
    ).json()
    before = client.get("/events").json()
    response = rename(client, series)
    assert response.status_code == 200, response.text
    plan = response.json()
    assert (
        len(plan["events"]) == 2 and plan["skipped_modified"] == 1 and plan["skipped_all_day"] == 0
    )
    assert client.get("/events").json() == before
    assert all(
        row["new_title"] == "כותרת חדשה למופעים"
        and row["start"] == row["new_start"]
        and row["end"] == row["new_end"]
        for row in plan["events"]
    )
    assert client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).json() == {
        "changed_count": 2
    }
    after = {row["id"]: row for row in client.get("/events").json()}
    for old in before:
        assert after[old["id"]] == (
            old if old["id"] == edited["id"] else {**old, "title": "כותרת חדשה למופעים"}
        )
    noop = rename(client, series).json()
    assert noop["id"] is None and noop["skipped_unchanged"] == 2 and noop["skipped_modified"] == 1
    included = rename(client, series, "All reviewed titles", include_modified=True).json()
    assert client.post("/recurrence/reschedules/confirm", json={"id": included["id"]}).json() == {
        "changed_count": 3
    }
    assert rename(client, series, "Another title").json()["skipped_modified"] == 1
    assert client.get("/recurrence/series").json()["items"][0]["title"] == "Clock change fixture"
    assert client.delete("/events/" + edited["id"]).status_code == 204
    assert client.post("/recurrence/reschedules/confirm", json={"id": included["id"]}).json() == {
        "changed_count": 3
    }


@pytest.mark.parametrize(
    "patch",
    [
        {"new_title": ""},
        {"new_title": "   "},
        {"new_title": "x" * 241},
        {"new_title": True},
        {"clock": "09:00", "duration": 60},
        {"day_shift": 1, "preserve_time": True},
        {"include_all_day": True},
    ],
)
def test_series_title_mode_validation_rejects_mixed_actions(client, monkeypatch, patch):
    series = prepared(client, monkeypatch)
    assert rename(client, series, **patch).status_code == 422
    assert len(client.get("/events").json()) == 3


def test_series_title_mixed_types_source_change_cancel_and_unknown_baseline(
    client, setup_app, monkeypatch
):
    from lifeos.series_models import SeriesOccurrence
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    series = prepared(client, monkeypatch, all_day=True)
    row = client.get("/events").json()[0]
    assert (
        client.put(
            "/events/" + row["id"],
            json={
                **row,
                "all_day": False,
                "start": "2026-10-28T09:00:00+02:00",
                "end": "2026-10-28T10:00:00+02:00",
            },
        ).status_code
        == 200
    )
    with Session(setup_app[0].state.assistant.engine) as db:
        link = db.scalar(select(SeriesOccurrence).where(SeriesOccurrence.event_id == row["id"]))
        link.original_signature = None
        db.commit()
    plan = rename(client, series, include_modified=True).json()
    assert len(plan["events"]) == 3 and sum(row["all_day"] for row in plan["events"]) == 2
    source = client.get("/events").json()[1]
    assert (
        client.put(
            "/events/" + source["id"], json={**source, "notes": "Changed after title review"}
        ).status_code
        == 200
    )
    before = client.get("/events").json()
    assert (
        client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).status_code == 409
    )
    assert client.get("/events").json() == before
    assert client.delete("/recurrence/reschedules/" + plan["id"]).status_code == 204
    assert (
        client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).status_code == 404
    )
    next_plan = rename(client, series, include_modified=True).json()
    assert client.post("/recurrence/reschedules/confirm", json={"id": next_plan["id"]}).json() == {
        "changed_count": 3
    }
    assert rename(client, series, "Next title").json()["skipped_modified"] == 2


def convert(client, series, target_all_day, **overrides):
    return client.post(
        f"/recurrence/series/{series}/reschedule-preview",
        json={
            "from_day": "2026-10-27",
            "target_all_day": target_all_day,
            **({"clock": "11:00", "duration": 90} if target_all_day is False else {}),
            **overrides,
        },
    )


@pytest.mark.parametrize("source_all_day", [False, True])
def test_series_type_conversion_requires_review_and_preserves_nontime_fields(
    client, monkeypatch, source_all_day
):
    series = prepared(client, monkeypatch, all_day=source_all_day)
    before = client.get("/events").json()
    noop = convert(client, series, source_all_day)
    assert noop.status_code == 200, noop.text
    assert noop.json()["id"] is None and noop.json()["skipped_unchanged"] == 3
    response = convert(client, series, not source_all_day)
    assert response.status_code == 200, response.text
    plan = response.json()
    assert len(plan["events"]) == 3
    first = plan["events"][0]
    assert first["all_day"] is source_all_day and first["new_all_day"] is not source_all_day
    assert (first["new_start"], first["new_end"]) == (
        ("2026-10-28T09:00:00Z", "2026-10-28T10:30:00Z")
        if source_all_day
        else ("2026-10-28", "2026-10-29")
    )
    assert client.get("/events").json() == before
    assert client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).json() == {
        "changed_count": 3
    }
    after = {row["id"]: row for row in client.get("/events").json()}
    for old in before:
        new = next(row for row in plan["events"] if row["id"] == old["id"])
        assert after[old["id"]] == {
            **old,
            "start": new["new_start"],
            "end": new["new_end"],
            "all_day": not source_all_day,
        }
    assert convert(client, series, source_all_day).json()["skipped_modified"] == 0
    assert client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).json() == {
        "changed_count": 3
    }


def test_type_conversion_protects_multiday_and_stale_sources(client, monkeypatch):
    series = prepared(client, monkeypatch, all_day=True)
    rows = client.get("/events").json()
    edited = client.put("/events/" + rows[0]["id"], json={**rows[0], "end": "2026-10-31"}).json()
    protected = convert(client, series, False).json()
    assert protected["skipped_modified"] == 1 and len(protected["events"]) == 2
    plan = convert(client, series, False, include_modified=True).json()
    assert plan["skipped_multiday"] == 1 and len(plan["events"]) == 2
    changed = rows[1]
    assert (
        client.put(
            "/events/" + changed["id"], json={**changed, "notes": "Changed conversion source"}
        ).status_code
        == 200
    )
    before = client.get("/events").json()
    assert (
        client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).status_code == 409
    )
    assert client.get("/events").json() == before
    fresh = convert(client, series, False, include_modified=True).json()
    assert client.post("/recurrence/reschedules/confirm", json={"id": fresh["id"]}).json() == {
        "changed_count": 2
    }
    assert next(row for row in client.get("/events").json() if row["id"] == edited["id"]) == edited


@pytest.mark.parametrize(
    "patch",
    [
        {"target_all_day": "true"},
        {"target_all_day": 1},
        {"target_all_day": False, "clock": None, "duration": None},
        {"clock": "09:00", "duration": 60},
        {"new_title": "Mixed"},
        {"preserve_time": True, "day_shift": 1},
        {"include_all_day": True},
    ],
)
def test_series_type_mode_rejects_invalid_or_compound_changes(client, monkeypatch, patch):
    series = prepared(client, monkeypatch)
    body = {"from_day": "2026-10-27", "target_all_day": True, **patch}
    assert (
        client.post(f"/recurrence/series/{series}/reschedule-preview", json=body).status_code == 422
    )


@pytest.mark.parametrize(
    "day,now,clock",
    [
        ("2026-10-25", "2026-10-24T06:00:00+00:00", "01:30"),
        ("2027-03-26", "2027-03-25T06:00:00+00:00", "02:30"),
    ],
)
def test_all_day_to_timed_rejects_ambiguous_or_missing_clock(client, monkeypatch, day, now, clock):
    series = prepared(client, monkeypatch, all_day=True, day=day, _now=datetime.fromisoformat(now))
    before = client.get("/events").json()
    response = convert(client, series, False, clock=clock, from_day=now[:10])
    assert response.status_code == 422, response.text
    assert client.get("/events").json() == before


@pytest.mark.parametrize("source_all_day", [False, True])
def test_type_conversion_postflush_checks_old_and_new_eligibility_types(
    client, setup_app, monkeypatch, source_all_day
):
    from lifeos import series_rescheduling
    from sqlalchemy import event

    series = prepared(client, monkeypatch, all_day=source_all_day)
    clock = [datetime(2026, 10, 28, 6, 59, 59, tzinfo=timezone.utc)]
    monkeypatch.setattr(series_rescheduling, "current_time", lambda: clock[0])
    plan = convert(
        client,
        series,
        not source_all_day,
        from_day="2026-10-28",
        **({"clock": "09:00", "duration": 60} if source_all_day else {}),
    )
    assert plan.status_code == 200, plan.text
    before = client.get("/events").json()
    engine = setup_app[0].state.assistant.engine
    flushed = []

    def crossed(connection, cursor, statement, parameters, context, many):
        if statement.startswith("UPDATE events"):
            flushed.append(True)
            clock[0] = datetime(2026, 10, 28, 7, tzinfo=timezone.utc)

    event.listen(engine, "after_cursor_execute", crossed)
    try:
        assert (
            client.post(
                "/recurrence/reschedules/confirm", json={"id": plan.json()["id"]}
            ).status_code
            == 409
        )
    finally:
        event.remove(engine, "after_cursor_execute", crossed)
    assert flushed and client.get("/events").json() == before
    clock[0] = datetime(2026, 10, 28, 6, 59, 59, tzinfo=timezone.utc)
    assert client.post(
        "/recurrence/reschedules/confirm", json={"id": plan.json()["id"]}
    ).json() == {"changed_count": 3}


@pytest.mark.parametrize("end,skipped", [("2026-10-29T00:00:00Z", 0), ("2026-10-29T00:01:00Z", 1)])
def test_conversion_midnight_is_exclusive_but_next_day_time_is_multiday(
    client, monkeypatch, end, skipped
):
    series = prepared(client, monkeypatch, timezone="UTC")
    row = client.get("/events").json()[0]
    assert (
        client.put(
            "/events/" + row["id"], json={**row, "start": "2026-10-28T23:00:00Z", "end": end}
        ).status_code
        == 200
    )
    response = convert(client, series, True, include_modified=True)
    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan["skipped_multiday"] == skipped and len(plan["events"]) == 3 - skipped
    if not skipped:
        reviewed = next(item for item in plan["events"] if item["id"] == row["id"])
        assert (reviewed["new_start"], reviewed["new_end"]) == ("2026-10-28", "2026-10-29")


def test_conversion_repeated_midnight_is_not_mistaken_for_start_of_day(client, monkeypatch):
    from zoneinfo import ZoneInfo

    series = prepared(
        client, monkeypatch, all_day=True, day="2026-10-31", timezone="America/Havana"
    )
    row = client.get("/events").json()[0]
    end = "2026-11-01T05:00:00Z"
    assert (
        datetime.fromisoformat(end.replace("Z", "+00:00"))
        .astimezone(ZoneInfo("America/Havana"))
        .fold
        == 1
    )
    assert (
        client.put(
            "/events/" + row["id"],
            json={**row, "all_day": False, "start": "2026-11-01T03:30:00Z", "end": end},
        ).status_code
        == 200
    )
    response = convert(client, series, True, include_modified=True)
    assert response.status_code == 200, response.text
    assert response.json()["id"] is None and response.json()["skipped_multiday"] == 1


def test_type_conversion_overflow_is_typed_and_leaves_all_sources_unchanged(client, monkeypatch):
    series = prepared(client, monkeypatch, timezone="UTC")
    row = client.get("/events").json()[0]
    assert (
        client.put(
            "/events/" + row["id"],
            json={**row, "start": "9999-12-31T09:00:00Z", "end": "9999-12-31T10:00:00Z"},
        ).status_code
        == 200
    )
    before = client.get("/events").json()
    response = convert(client, series, True, include_modified=True)
    assert response.status_code == 422 and response.json()["detail"] == "series_time_invalid"
    assert client.get("/events").json() == before


@pytest.mark.parametrize(
    "day,now,clock",
    [
        ("2026-10-25", "2026-10-24T06:00:00+00:00", "00:30"),
        ("2027-03-26", "2027-03-25T06:00:00+00:00", "01:30"),
    ],
)
def test_converted_duration_is_actual_elapsed_minutes_across_dst(
    client, monkeypatch, day, now, clock
):
    series = prepared(client, monkeypatch, all_day=True, day=day, _now=datetime.fromisoformat(now))
    response = convert(client, series, False, clock=clock, duration=180, from_day=now[:10])
    assert response.status_code == 200, response.text
    row = response.json()["events"][0]
    begin = datetime.fromisoformat(row["new_start"].replace("Z", "+00:00"))
    finish = datetime.fromisoformat(row["new_end"].replace("Z", "+00:00"))
    assert finish - begin == timedelta(minutes=180)


def combined(client, series, **overrides):
    return client.post(
        f"/recurrence/series/{series}/reschedule-preview",
        json={
            "from_day": "2026-10-27",
            "shift_and_time": True,
            "day_shift": 2,
            "clock": "14:00",
            "duration": 45,
            **overrides,
        },
    )


def test_explicit_combined_dates_and_clocks_preserve_protected_records(client, monkeypatch):
    series = prepared(client, monkeypatch)
    rows = client.get("/events").json()
    edited = client.put(
        "/events/" + rows[1]["id"], json={**rows[1], "notes": "Protected combined fixture"}
    ).json()
    before = client.get("/events").json()
    response = combined(client, series)
    assert response.status_code == 200, response.text
    plan = response.json()
    assert len(plan["events"]) == 2 and plan["skipped_modified"] == 1
    assert plan["events"][0]["new_start"] == "2026-10-30T12:00:00Z"
    assert plan["events"][0]["new_end"] == "2026-10-30T12:45:00Z"
    assert client.get("/events").json() == before
    assert client.post("/recurrence/reschedules/confirm", json={"id": plan["id"]}).json() == {
        "changed_count": 2
    }
    after = {row["id"]: row for row in client.get("/events").json()}
    for old in before:
        expected = next((row for row in plan["events"] if row["id"] == old["id"]), None)
        assert after[old["id"]] == (
            {**old, "start": expected["new_start"], "end": expected["new_end"]}
            if expected
            else edited
        )
    assert combined(client, series).json()["skipped_modified"] == 1


@pytest.mark.parametrize(
    "patch",
    [
        {"shift_and_time": False},
        {"day_shift": 0},
        {"preserve_time": True},
        {"target_all_day": True},
        {"new_title": "Mixed"},
        {"include_all_day": True},
    ],
)
def test_combined_time_mode_does_not_implicitly_mix_operations(client, monkeypatch, patch):
    series = prepared(client, monkeypatch)
    assert combined(client, series, **patch).status_code == 422


def test_combined_time_uses_elapsed_duration_and_skips_all_day(client, monkeypatch):
    now = datetime(2026, 10, 20, 6, tzinfo=timezone.utc)
    series = prepared(client, monkeypatch, day="2026-10-24", _now=now)
    plan = combined(client, series, day_shift=1, clock="00:30", duration=180, from_day="2026-10-20")
    assert plan.status_code == 200, plan.text
    row = plan.json()["events"][0]
    assert (row["new_start"], row["new_end"]) == ("2026-10-24T21:30:00Z", "2026-10-25T00:30:00Z")
    assert (
        combined(client, series, day_shift=1, clock="01:30", from_day="2026-10-20").status_code
        == 422
    )
    all_day = prepared(client, monkeypatch, all_day=True)
    empty = combined(client, all_day).json()
    assert empty["id"] is None and empty["skipped_all_day"] == 3
