import pytest
from lifeos.account_records import AccountRecords
from lifeos.accounts import AccountService
from lifeos.models import Account
from sqlalchemy.orm import Session


def test_owned_lists_preserve_existing_read_budget(client, setup_app, monkeypatch):
    from fastapi import HTTPException
    from lifeos import academic_reads

    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    owner = auth.register("bounded-owner", "fixture password")
    records = AccountRecords(engine)
    records.save(owner, "tasks", {"title": "First"})
    records.save(owner, "tasks", {"title": "Second"})
    monkeypatch.setattr(academic_reads, "MAX_RECORDS", 1)
    with pytest.raises(HTTPException) as error:
        records.list(owner, "tasks")
    assert error.value.status_code == 503


@pytest.mark.parametrize(
    "kind,body",
    [
        ("tasks", {"title": "Private task fixture", "due": "2026-10-29"}),
        (
            "events",
            {
                "title": "Private event fixture",
                "start": "2026-10-29",
                "end": "2026-10-30",
                "all_day": True,
            },
        ),
    ],
)
def test_manual_records_are_scoped_for_two_accounts_and_legacy(client, setup_app, kind, body):
    engine = setup_app[0].state.assistant.engine
    accounts = AccountService(engine, enabled=True)
    a = accounts.register("a-fixture", "fixture password a")
    b = accounts.register("b-fixture", "fixture password b")
    store = AccountRecords(engine)
    legacy = client.post("/" + kind, json=body)
    assert legacy.status_code == 201
    owned = store.save(a, kind, {**body, "account_id": b})
    assert [row["id"] for row in store.list(a, kind)] == [owned["id"]]
    assert store.list(b, kind) == []
    with pytest.raises(LookupError):
        store.save(b, kind, body, owned["id"])
    with pytest.raises(LookupError):
        store.delete(b, kind, owned["id"])
    with pytest.raises(LookupError):
        store.delete(a, kind, legacy.json()["id"])
    changed = store.save(a, kind, {**body, "title": "Edited fixture"}, owned["id"])
    assert changed["title"] == "Edited fixture"
    store.delete(a, kind, owned["id"])
    assert store.list(a, kind) == []
    with Session(engine) as db:
        db.get(Account, a).enabled = False
        db.commit()
    with pytest.raises(PermissionError):
        store.list(a, kind)
