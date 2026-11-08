from datetime import datetime, timezone

import pytest
from lifeos.academic_models import AcademicItem
from lifeos.account_academic import AccountAcademic
from lifeos.account_planning import AccountPlanning
from lifeos.account_records import AccountRecords
from lifeos.account_snapshot import AccountSnapshot
from lifeos.accounts import AccountService
from lifeos.models import Task
from sqlalchemy.orm import Session


def test_exams_remain_academic_calendar_dates_not_actionable_tasks(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    owner = auth.register("exam-separation", "fixture exam password")
    session = auth.login("exam-separation", "fixture exam password")
    academic = AccountAcademic(engine)
    term = academic.save_root(owner, "terms", {"name": "Fixture term", "start_date": "2026-10-01", "end_date": "2027-04-01"})
    course = academic.save_root(owner, "courses", {"term_id": term["id"], "name": "Systems fixture"})
    assignment = academic.save_child(owner, "items", {"course_id": course["id"], "title": "Assignment fixture", "kind": "assignment", "due": "2026-11-05"})
    exam = academic.save_child(owner, "items", {"course_id": course["id"], "title": "Exam four months away", "kind": "exam", "due": "2027-03-04"})
    records = AccountRecords(engine)
    assert [row["id"] for row in records.list(owner, "tasks")] == [assignment["task_id"]]
    snapshot = AccountSnapshot(engine).build(owner)
    assert [row["id"] for row in snapshot["tasks"]] == [assignment["task_id"]]
    assert any(row["source"] == "exam" and row["academic_id"] == exam["id"] for row in snapshot["events"])
    with Session(engine) as db:
        assert db.get(AcademicItem, exam["id"]) is not None
        assert db.get(AcademicItem, assignment["id"]) is not None
        assert db.get(Task, exam["task_id"]).completed is False
    with pytest.raises(LookupError):
        records.save(owner, "tasks", {"title": exam["title"], "due": exam["due"], "completed": True}, exam["task_id"])
    with pytest.raises(LookupError):
        AccountPlanning(engine).propose(owner, session["token"], {"task_id": exam["task_id"], "day": "2026-11-04"}, now=datetime(2026, 11, 4, 6, tzinfo=timezone.utc))
