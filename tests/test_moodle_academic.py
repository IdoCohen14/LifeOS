import httpx
import pytest
from lifeos.academic_models import AcademicItem
from lifeos.account_academic import AccountAcademic
from lifeos.account_moodle import AccountMoodle
from lifeos.account_records import AccountRecords
from lifeos.account_snapshot import AccountSnapshot
from lifeos.accounts import AccountService
from lifeos.braude_academic import BraudeAcademic
from lifeos.models import Task
from lifeos.moodle_academic import deadline_title
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from test_braude_academic import roster_file


def test_submission_language_excludes_opening_grading_and_general_events():
    assert deadline_title("יש להגיש את 'מעבדה 1'") == "מעבדה 1"
    assert deadline_title("Lab 1 is due") == "Lab 1"
    assert deadline_title("Lab 1 is due (extension)") == "Lab 1"
    assert deadline_title("Lab 1 - Group A (Due date)") == "Lab 1 - Group A"
    assert deadline_title("Lab 1 - Override (Due date)") == "Lab 1 - Override"
    for title in ["Lab 1", "Lab 1 opens", "Lab 1 is due to be graded", "Quiz closes", "Lab 1 (Grading due date)"]:
        assert deadline_title(title) is None


@pytest.mark.parametrize("all_day", [False, True])
def test_sync_materializes_home_task_and_course_deadline_once(client, setup_app, tmp_path, all_day):
    engine, directory = setup_app[0].state.assistant.engine, setup_app[1]
    accounts = AccountService(engine, enabled=True)
    owner = accounts.register("assignment-owner", "fixture password")
    other = accounts.register("assignment-other", "fixture password")
    BraudeAcademic(engine).import_roster(owner, roster_file(tmp_path), year=2027, semester=1,
                                       start_date="2026-10-02", end_date="2027-01-30")
    store = AccountMoodle(engine, directory)
    store.configure(owner, "moodle", {"url": "https://moodle27.braude.ac.il/calendar/export_execute.php?authtoken=fixture"})
    values = {"uid": "one", "day": "20261105", "category": "Course (2027_1_6_12345)", "summary": "יש להגיש את 'מעבדה 1'"}

    def factory(**kwargs):
        def handler(request):
            start = f"DTSTART;VALUE=DATE:{values['day']}" if all_day else f"DTSTART:{values['day']}T200000Z"
            raw = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:" + values['uid'] + "@moodle27.braude.ac.il\r\n"
                   + start + "\r\nSUMMARY:" + values["summary"] + "\r\nCATEGORIES:" + values["category"]
                   + "\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
            return httpx.Response(200, content=raw.encode())
        return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)

    def sync():
        store.sync(owner, client_factory=factory)

    sync()
    sync()
    records = AccountRecords(engine)
    tasks = records.list(owner, "tasks")
    due = "2026-11-05" if all_day else "2026-11-05T20:00:00Z"
    assert len(tasks) == 1 and tasks[0]["due"] == due and tasks[0]["academic_id"]
    assert tasks[0]["academic_kind"] == "assignment" and tasks[0]["academic_course_name"] == "קורס דמה"
    assert records.list(other, "tasks") == []
    assert AccountAcademic(engine).list_children(other, "items") == []
    assert len(AccountAcademic(engine).list_children(owner, "items")) == 1
    assert store.records(owner, "moodle")[0]["academic_id"] == tasks[0]["academic_id"]
    assert store.records(owner, "moodle", calendar_only=True) == []
    snapshot = AccountSnapshot(engine).build(owner)
    assert len(snapshot["events"]) == 1 and snapshot["events"][0]["source"] == "assignment"
    # Home checkbox changes only completion, not the academic record fields.
    records.save(owner, "tasks", {**tasks[0], "completed": True}, tasks[0]["id"])
    with pytest.raises(ValueError):
        records.save(owner, "tasks", {**tasks[0], "title": "overwrite"}, tasks[0]["id"])
    values["day"] = "20261106"
    sync()
    task = records.list(owner, "tasks")[0]
    assert task["completed"] and task["due"].startswith("2026-11-06")
    assert AccountSnapshot(engine).build(owner)["events"] == []
    # Local edits survive source refresh; completed remains completed.
    with Session(engine) as db:
        item = db.scalar(select(AcademicItem))
        item.due = item.task.due = "2026-11-07"
        db.commit()
    values["day"] = "20261108"
    sync()
    assert records.list(owner, "tasks")[0]["due"] == "2026-11-07"
    # Local deletion is remembered; source is visible without recreating a task.
    with Session(engine) as db:
        db.execute(delete(AcademicItem))
        db.execute(delete(Task).where(Task.account_id == owner))
        db.commit()
    sync()
    assert records.list(owner, "tasks") == []
    assert len(store.records(owner, "moodle", calendar_only=True)) == 1
    # General event, wrong semester/course never silently becomes a task.
    values.update(uid="wrong-semester", category="Course (2028_1_6_12345)")
    sync()
    assert records.list(owner, "tasks") == []
    values.update(uid="general-event", category="Course (2027_1_6_12345)", summary="Lab opens")
    sync()
    assert records.list(owner, "tasks") == []
    # Lost provider lease cannot create a task or advance source memory.
    lease = store.begin_sync(owner, "moodle")
    store.configure(owner, "moodle", {"url": "fixture replacement"})
    proposed = {"id": "moodle-new", "title": "New is due", "start": due,
                "course_categories": ["Course (2027_1_6_12345)"]}
    with pytest.raises(RuntimeError, match="ownership lost"):
        store.commit_sync(owner, "moodle", lease["owner"], lease["revision"], [proposed])
    assert records.list(owner, "tasks") == []
