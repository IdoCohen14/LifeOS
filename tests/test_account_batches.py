import pytest
from fastapi import HTTPException
from lifeos.account_academic import AccountAcademic
from lifeos.account_batches import AccountBatches
from lifeos.accounts import AccountService


def test_owned_course_and_timetable_capture_rejects_foreign_parent_and_session(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    a = auth.register("batch-a", "fixture password a")
    b = auth.register("batch-b", "fixture password b")
    token = auth.login("batch-a", "fixture password a")["token"]
    other = auth.login("batch-b", "fixture password b")["token"]
    academic = AccountAcademic(engine)
    term = academic.save_root(
        a, "terms", {"name": "Term", "start_date": "2026-11-01", "end_date": "2027-01-31"}
    )
    service = AccountBatches(engine)
    body = {"term_id": term["id"], "rows": [{"name": "Course A"}, {"name": "Course B"}]}
    with pytest.raises(HTTPException):
        service.preview(b, other, "courses", body)
    preview = service.preview(a, token, "courses", body)
    assert academic.list_roots(a, "courses") == []
    with pytest.raises(PermissionError):
        service.confirm(a, other, "courses", preview["id"])
    saved = service.confirm(a, token, "courses", preview["id"])
    assert saved["created_count"] == 2
    assert service.confirm(a, token, "courses", preview["id"]) == saved
    slots = service.preview(
        a,
        token,
        "timetable",
        {
            "course_id": saved["ids"][0],
            "weekdays": [0, 2],
            "start_time": "09:00",
            "end_time": "10:00",
            "timezone": "Asia/Jerusalem",
        },
    )
    assert service.confirm(a, token, "timetable", slots["id"])["created_count"] == 2
    assert len(academic.list_children(a, "timetable")) == 2
    assert academic.list_children(b, "timetable") == []
