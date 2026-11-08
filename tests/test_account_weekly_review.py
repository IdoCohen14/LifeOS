import pytest
from lifeos.account_records import AccountRecords
from lifeos.accounts import AccountService
from lifeos.weekly_review import WeeklyReviewService


def test_weekly_review_filters_task_history_and_current_counts(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    a = auth.register("review-a", "fixture password a")
    b = auth.register("review-b", "fixture password b")
    records = AccountRecords(engine)
    task = records.save(a, "tasks", {"title": "Only A"})
    records.save(a, "tasks", {"title": "Only A", "completed": True}, task["id"])
    records.save(b, "tasks", {"title": "Only B", "completed": True})
    client.post("/tasks", json={"title": "Legacy", "completed": True})
    review = WeeklyReviewService(engine).review(account_id=a)
    assert review["completed"] == 1 and review["transition_count"] == 1
    assert [row["title"] for row in review["recent"]] == ["Only A"]
    records.save(a, "tasks", {"title": "Only A", "completed": False}, task["id"])
    assert WeeklyReviewService(engine).review(account_id=a)["reopened"] == 1
    legacy = client.get("/review/weekly").json()
    assert legacy["completed"] == 1 and legacy["recent"][0]["title"] == "Legacy"
    with pytest.raises(PermissionError):
        WeeklyReviewService(engine).review(account_id="missing")
