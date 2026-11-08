from datetime import datetime, timezone

from lifeos.account_braude import AccountBraude
from lifeos.account_moodle import AccountMoodle
from lifeos.account_planning import AccountPlanning
from lifeos.account_records import AccountRecords
from lifeos.account_snapshot import AccountSnapshot
from lifeos.accounts import AccountService
from lifeos.braude_academic import BraudeAcademic
from test_braude_academic import roster_file
from test_moodle_versions import event, feed


def test_imported_assignment_to_confirmed_time_block_and_daily_weekly_completion(client, setup_app, tmp_path):
    engine, directory = setup_app[0].state.assistant.engine, setup_app[1]
    auth = AccountService(engine, enabled=True)
    owner = auth.register("daily-flow", "fixture password")
    other = auth.register("daily-other", "fixture password")
    session = auth.login("daily-flow", "fixture password")
    BraudeAcademic(engine).import_roster(owner, roster_file(tmp_path), year=2027, semester=1,
                                       start_date="2026-10-02", end_date="2027-01-30")
    braude, moodle = AccountBraude(engine, directory), AccountMoodle(engine, directory)
    for provider, store, rows in [
        ("braude", braude, [{"id": "class-fixture", "source": "braude", "title": "קורס דמה",
            "notes": "הרצאה\nחדר: M209", "start": "2026-11-05T06:00:00Z",
            "end": "2026-11-05T08:00:00Z", "all_day": False, "created_at": "2026-01-01T00:00:00Z"}]),
        ("moodle", moodle, moodle.parse_events(feed(event()), "moodle27.braude.ac.il")),
    ]:
        store.configure(owner, provider, {"url": "fixture"})
        lease = store.begin_sync(owner, provider)
        store.commit_sync(owner, provider, lease["owner"], lease["revision"], rows)
    now = datetime(2026, 11, 5, 4, tzinfo=timezone.utc)
    records, snapshot = AccountRecords(engine), AccountSnapshot(engine)
    task = records.list(owner, "tasks")[0]
    assert task["academic_kind"] == "assignment" and task["academic_course_name"] == "קורס דמה"
    assert snapshot.briefing(owner, now=now)["deadlines"] == 1
    planning = AccountPlanning(engine)
    proposal = planning.propose(owner, session["token"], {"task_id": task["id"], "day": "2026-11-05",
        "duration": 30, "window_start": "08:00", "window_end": "12:00"}, now=now)["proposal"]
    assert records.list(owner, "events") == []
    saved = planning.confirm(owner, session["token"], proposal["id"], now=now)
    assert datetime.fromisoformat(saved["start"]) == datetime(2026, 11, 5, 8, tzinfo=timezone.utc)
    assert planning.confirm(owner, session["token"], proposal["id"], now=now) == saved
    for days in (1, 7):
        summary = snapshot.briefing(owner, days, now=now)
        assert summary["events"] == 2 and summary["minutes"] == 150
        assert summary["deadlines"] == 1
    records.save(owner, "tasks", {**task, "completed": True}, task["id"])
    assert snapshot.briefing(owner, now=now)["deadlines"] == 0
    assert snapshot.briefing(owner, 7, now=now)["deadlines"] == 0
    assert len(snapshot.build(owner)["events"]) == 2  # Class + actual work, no completed deadline copy.
    assert snapshot.build(other)["tasks"] == [] and snapshot.build(other)["events"] == []
