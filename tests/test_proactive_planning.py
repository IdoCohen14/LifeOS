from datetime import datetime, timedelta, timezone

import pytest
from lifeos.account_planning import AccountPlanning
from lifeos.account_preferences import AccountPreferences
from lifeos.account_records import AccountRecords
from lifeos.accounts import AccountService
from lifeos.proactive_planning import ProactivePlanning


def state(setup_app):
    engine = setup_app[0].state.assistant.engine
    accounts = AccountService(engine, enabled=True)
    owner = accounts.register("proactive-owner", "fixture password")
    other = accounts.register("proactive-other", "fixture password")
    token = accounts.login("proactive-owner", "fixture password")["token"]
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
        days=1
    )
    task = AccountRecords(engine).save(
        owner,
        "tasks",
        {"title": "Upcoming owned fixture", "due": (now + timedelta(days=2)).date().isoformat()},
    )
    return engine, owner, other, token, task, now


def test_read_only_owned_suggestion_and_reviewed_save(client, setup_app):
    engine, owner, other, token, task, now = state(setup_app)
    planner = ProactivePlanning(engine)
    for index in range(21):
        AccountRecords(engine).save(
            owner, "tasks", {"title": f"Old fixture {index}", "due": "2000-01-01"}
        )
    candidate = planner.suggestion(owner, now=now)["suggestion"]
    assert candidate["task_id"] == task["id"]
    assert candidate["duration"] == 30 and not candidate["preferences_used"]
    assert planner.suggestion(other, now=now)["suggestion"] is None
    assert not AccountRecords(engine).list(owner, "events")
    review = planner.propose(owner, token, candidate["id"], now=now)
    assert datetime.fromisoformat(
        review["proposal"]["record"]["start"].replace("Z", "+00:00")
    ) == datetime.fromisoformat(candidate["start"])
    assert not AccountRecords(engine).list(owner, "events")
    saved = AccountPlanning(engine).confirm(owner, token, review["proposal"]["id"], now=now)
    assert datetime.fromisoformat(saved["start"].replace("Z", "+00:00")) == datetime.fromisoformat(
        candidate["start"]
    )
    assert planner.suggestion(owner, now=now)["suggestion"] is None
    assert not AccountRecords(engine).list(owner, "tasks")[0]["completed"]


def test_preference_and_source_changes_invalidate_proactive_review(client, setup_app):
    from lifeos.models import AccountProvider
    from sqlalchemy.orm import Session

    engine, owner, _, token, _, now = state(setup_app)
    planner = ProactivePlanning(engine)
    candidate = planner.suggestion(owner, now=now)["suggestion"]
    review = planner.propose(owner, token, candidate["id"], now=now)
    AccountPreferences(engine).put(owner, "planning", {"enabled": True, "duration": 60}, 0)
    with pytest.raises(ValueError):
        AccountPlanning(engine).confirm(owner, token, review["proposal"]["id"], now=now)
    with Session(engine) as db:
        db.add(
            AccountProvider(
                account_id=owner, provider="google", credentials=b"synthetic", last_success=None
            )
        )
        db.commit()
    response = planner.suggestion(owner, now=now)
    assert response["suggestion"] is None and response["reason"] == "stale_sources"
    assert "google" in response["stale_sources"]


def test_source_failure_after_review_keeps_calendar_unchanged(client, setup_app):
    from lifeos.models import AccountProvider
    from sqlalchemy.orm import Session

    engine, owner, _, token, _, now = state(setup_app)
    with Session(engine) as db:
        db.add(
            AccountProvider(
                account_id=owner,
                provider="google",
                credentials=b"synthetic",
                last_success=int(now.timestamp()),
            )
        )
        db.commit()
    planner = ProactivePlanning(engine)
    candidate = planner.suggestion(owner, now=now)["suggestion"]
    review = planner.propose(owner, token, candidate["id"], now=now)
    with Session(engine) as db:
        db.get(AccountProvider, (owner, "google")).error = "fixture_disconnected"
        db.commit()
    with pytest.raises(ValueError):
        AccountPlanning(engine).confirm(owner, token, review["proposal"]["id"], now=now)
    assert not AccountRecords(engine).list(owner, "events")


def test_exam_not_treated_as_assignment_and_existing_busy_time_is_respected(client, setup_app):
    from lifeos.account_academic import AccountAcademic

    engine, owner, _, _, task, now = state(setup_app)
    AccountRecords(engine).delete(owner, "tasks", task["id"])
    academic = AccountAcademic(engine)
    term = academic.save_root(
        owner,
        "terms",
        {
            "name": "Fixture term",
            "start_date": now.date().isoformat(),
            "end_date": (now + timedelta(days=30)).date().isoformat(),
        },
    )
    course = academic.save_root(owner, "courses", {"name": "Fixture course", "term_id": term["id"]})
    academic.save_child(
        owner,
        "items",
        {
            "title": "Exam fixture",
            "course_id": course["id"],
            "kind": "exam",
            "due": (now + timedelta(days=2)).date().isoformat(),
        },
    )
    planner = ProactivePlanning(engine)
    assert planner.suggestion(owner, now=now)["suggestion"] is None
    academic.save_child(
        owner,
        "items",
        {
            "title": "Assignment fixture",
            "course_id": course["id"],
            "kind": "assignment",
            "due": (now + timedelta(days=3)).date().isoformat(),
        },
    )
    candidate = planner.suggestion(owner, now=now)["suggestion"]
    assert candidate["course_name"] == "Fixture course"
    AccountRecords(engine).save(
        owner,
        "events",
        {"title": "Busy fixture", "start": candidate["start"], "end": candidate["end"]},
    )
    changed = planner.suggestion(owner, now=now)["suggestion"]
    assert changed["start"] != candidate["start"]


def test_task_changed_during_review_cannot_silently_change_displayed_proposal(
    client, setup_app, monkeypatch
):
    engine, owner, _, token, task, now = state(setup_app)
    planner = ProactivePlanning(engine)
    candidate = planner.suggestion(owner, now=now)["suggestion"]
    original = AccountPlanning.propose

    def changed(service, account_id, session_token, body, **kwargs):
        AccountRecords(engine).save(
            owner, "tasks", {"title": "Changed during review", "due": task["due"]}, task["id"]
        )
        return original(service, account_id, session_token, body, **kwargs)

    monkeypatch.setattr(AccountPlanning, "propose", changed)
    with pytest.raises(ValueError):
        planner.propose(owner, token, candidate["id"], now=now)
    assert not AccountRecords(engine).list(owner, "events")


def test_reviewed_move_preserves_existing_block_until_confirmation(client, setup_app):
    from zoneinfo import ZoneInfo

    engine, owner, _, token, task, now = state(setup_app)
    today = now.astimezone(ZoneInfo("Asia/Jerusalem")).date()
    original = AccountPlanning(engine).propose(
        owner,
        token,
        {"task_id": task["id"], "day": (today + timedelta(days=1)).isoformat()},
        now=now,
    )
    saved = AccountPlanning(engine).confirm(owner, token, original["proposal"]["id"], now=now)
    records = AccountRecords(engine)
    event = records.list(owner, "events")[0]
    records.save(
        owner,
        "events",
        {
            "title": event["title"],
            "notes": "Preserve my notes",
            "start": event["start"],
            "end": event["end"],
        },
        event["id"],
    )
    records.save(owner, "tasks", {"title": task["title"], "due": today.isoformat()}, task["id"])
    planner = ProactivePlanning(engine)
    suggestion = planner.suggestion(owner, now=now)["suggestion"]
    assert suggestion["replacement"]["id"] == saved["id"]
    assert suggestion["reason"] == "after_deadline"
    from lifeos.account_notices import AccountNotices
    from lifeos.account_requests import AccountRequests
    from lifeos.security import token_hash

    requests = AccountRequests(engine)
    notice = next(
        row
        for row in AccountNotices(engine).feed(owner)["items"]
        if task["id"] in row["source_ids"]
    )
    tracked = requests.create(owner, notice["id"])
    review = planner.propose(owner, token, suggestion["id"], now=now)
    resumed = requests.get(owner, tracked["id"], token_hash(token))
    assert resumed["resume_proposal"]["change_from"]["start"] == saved["start"]
    assert resumed["resume_proposal"]["kind"] == "event"
    assert records.list(owner, "events")[0]["start"] == saved["start"]
    moved = AccountPlanning(engine).confirm(owner, token, review["proposal"]["id"], now=now)
    assert moved["id"] == saved["id"] and moved["start"] != saved["start"]
    assert len(records.list(owner, "events")) == 1
    assert records.list(owner, "events")[0]["notes"] == "Preserve my notes"


def test_conflicting_block_edits_and_in_progress_work_are_not_overwritten(client, setup_app):
    from zoneinfo import ZoneInfo

    engine, owner, _, token, task, now = state(setup_app)
    tomorrow = now.astimezone(ZoneInfo("Asia/Jerusalem")).date() + timedelta(days=1)
    planning = AccountPlanning(engine)
    original = planning.propose(
        owner, token, {"task_id": task["id"], "day": tomorrow.isoformat()}, now=now
    )
    saved = planning.confirm(owner, token, original["proposal"]["id"], now=now)
    records = AccountRecords(engine)
    records.save(
        owner, "events", {"title": "New conflict", "start": saved["start"], "end": saved["end"]}
    )
    planner = ProactivePlanning(engine)
    suggestion = planner.suggestion(owner, now=now)["suggestion"]
    assert suggestion["reason"] == "calendar_conflict"
    review = planner.propose(owner, token, suggestion["id"], now=now)
    records.save(
        owner,
        "events",
        {"title": "Manual edit wins", "start": saved["start"], "end": saved["end"]},
        saved["id"],
    )
    with pytest.raises(ValueError):
        planning.confirm(owner, token, review["proposal"]["id"], now=now)
    assert (
        next(row for row in records.list(owner, "events") if row["id"] == saved["id"])["title"]
        == "Manual edit wins"
    )
    in_progress = datetime.fromisoformat(saved["start"].replace("Z", "+00:00")) + timedelta(
        minutes=1
    )
    assert planner.suggestion(owner, now=in_progress)["suggestion"] is None
