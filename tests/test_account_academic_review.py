from datetime import datetime, timedelta, timezone

from lifeos.academic_review import academic_snapshot
from lifeos.account_academic import AccountAcademic
from lifeos.accounts import AccountService


def test_academic_review_uses_only_owned_grades_and_deadlines(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    a = auth.register("academic-review-a", "fixture password a")
    b = auth.register("academic-review-b", "fixture password b")
    store = AccountAcademic(engine)
    due = (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()
    for owner in (a, b):
        term = store.save_root(
            owner, "terms", {"name": "Term", "start_date": "2026-10-01", "end_date": "2027-01-31"}
        )
        course = store.save_root(owner, "courses", {"term_id": term["id"], "name": owner})
        store.save_child(
            owner, "items", {"course_id": course["id"], "title": owner, "kind": "exam", "due": due}
        )
        store.save_child(
            owner,
            "grades",
            {"course_id": course["id"], "title": "Grade", "score": 80, "weight": 50},
        )
    summary = academic_snapshot(engine, account_id=a)
    assert len(summary["grades"]) == 1 and summary["grades"][0]["course_name"] == a
    assert [row["title"] for row in summary["upcoming_exams"]] == [a]
    legacy = academic_snapshot(engine)
    assert legacy["grades"] == [] and legacy["upcoming_exams"] == []
