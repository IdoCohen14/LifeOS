import base64

import pytest
from lifeos.account_academic import AccountAcademic
from lifeos.accounts import AccountService


def test_owned_terms_courses_and_parent_reassignment_are_isolated(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    accounts = AccountService(engine, enabled=True)
    a = accounts.register("academic-a", "fixture password a")
    b = accounts.register("academic-b", "fixture password b")
    store = AccountAcademic(engine)
    body = {"name": "Term fixture", "start_date": "2026-10-01", "end_date": "2027-01-31"}
    ta = store.save_root(a, "terms", body)
    tb = store.save_root(b, "terms", body)
    course = store.save_root(a, "courses", {"name": "Course fixture", "term_id": ta["id"]})
    assert store.list_roots(b, "courses") == []
    assert [term["id"] for term in store.list_roots(a, "terms")] == [ta["id"]]
    for owner, term in [(b, ta), (a, tb)]:
        with pytest.raises(LookupError):
            store.save_root(owner, "courses", {"name": "Forbidden", "term_id": term["id"]})
    with pytest.raises(LookupError):
        store.save_root(b, "courses", {"name": "Forbidden", "term_id": tb["id"]}, course["id"])
    with pytest.raises(LookupError):
        store.save_root(a, "courses", {"name": "Forbidden", "term_id": tb["id"]}, course["id"])
    assert store.list_roots(a, "courses")[0]["term_id"] == ta["id"]
    item = store.save_child(
        a, "items", {"course_id": course["id"], "title": "Assignment fixture", "due": "2026-11-01"}
    )
    from lifeos.account_records import AccountRecords

    tasks = AccountRecords(engine)
    assert tasks.list(a, "tasks")[0]["id"] == item["task_id"]
    assert tasks.list(b, "tasks") == []
    with pytest.raises(LookupError):
        store.save_child(
            b, "items", {"course_id": course["id"], "title": "Forbidden", "due": "2026-11-01"}
        )
    with pytest.raises(LookupError):
        store.save_child(
            b,
            "items",
            {"course_id": course["id"], "title": "Forbidden", "due": "2026-11-01"},
            item["id"],
        )
    store.save_child(
        a,
        "items",
        {
            "course_id": course["id"],
            "title": "Completed fixture",
            "due": "2026-11-01",
            "completed": True,
        },
        item["id"],
    )
    assert tasks.list(a, "tasks")[0]["completed"] is True
    store.save_child(
        a,
        "grades",
        {"course_id": course["id"], "title": "Grade fixture", "score": 90, "weight": 70},
    )
    with pytest.raises(ValueError):
        store.save_child(
            a,
            "grades",
            {"course_id": course["id"], "title": "Overflow fixture", "score": 80, "weight": 40},
        )
    assert store.list_children(b, "items") == []
    assert store.list_children(b, "grades") == []
    assert len(store.list_children(a, "items")) == 1
    with pytest.raises(LookupError):
        store.delete_academic(b, "items", item["id"])
    with pytest.raises(ValueError):
        store.delete_academic(a, "courses", course["id"])
    store.delete_academic(a, "items", item["id"])
    assert tasks.list(a, "tasks") == []
    assert store.list_children(a, "items") == []
    grade = store.list_children(a, "grades")[0]
    store.delete_academic(a, "grades", grade["id"])
    store.delete_academic(a, "courses", course["id"])
    store.delete_academic(a, "terms", ta["id"])
    assert store.list_roots(a, "terms") == []
    assert len(store.list_roots(b, "terms")) == 1


def test_owned_documents_cannot_leak_through_search_detail_download_or_delete(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    accounts = AccountService(engine, enabled=True)
    a = accounts.register("document-a", "fixture password a")
    b = accounts.register("document-b", "fixture password b")
    store = AccountAcademic(engine)
    term = store.save_root(
        a, "terms", {"name": "Document term", "start_date": "2026-10-01", "end_date": "2027-01-31"}
    )
    course = store.save_root(a, "courses", {"name": "Document course", "term_id": term["id"]})
    content = b"uniquedocumentfixture searchable text"
    body = {
        "course_id": course["id"],
        "filename": "fixture.txt",
        "content_base64": base64.b64encode(content).decode(),
    }
    with pytest.raises(LookupError):
        store.upload_document(b, body)
    document = store.upload_document(a, body)
    assert store.search_documents(a, "uniquedocumentfixture")[0]["document_id"] == document["id"]
    assert store.search_documents(b, "uniquedocumentfixture") == []
    assert store.document(a, document["id"], download=True) == ("fixture.txt", content)
    assert store.document(a, document["id"])["sections"][0]["text"] == content.decode()
    with pytest.raises(LookupError):
        store.document(b, document["id"])
    with pytest.raises(LookupError):
        store.document(b, document["id"], download=True)
    with pytest.raises(LookupError):
        store.delete_academic(b, "documents", document["id"])
    store.delete_academic(a, "documents", document["id"])
    assert store.search_documents(a, "uniquedocumentfixture") == []
