import pytest
from lifeos.account_providers import AccountProviders
from lifeos.accounts import AccountService
from lifeos.models import AccountProvider
from sqlalchemy.orm import Session


def test_provider_cache_credentials_and_stale_sync_are_account_scoped(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    accounts = AccountService(engine, enabled=True)
    a = accounts.register("provider-a", "fixture password a")
    b = accounts.register("provider-b", "fixture password b")
    store = AccountProviders(engine, setup_app[1])
    for owner in (a, b):
        store.configure(owner, "gmail", {"refresh_token": "secret-fixture-" + owner})
        lease = store.begin_sync(owner, "gmail")
        assert lease["credentials"]["refresh_token"] == "secret-fixture-" + owner
        store.commit_sync(
            owner,
            "gmail",
            lease["owner"],
            lease["revision"],
            [{"id": "same-id", "subject": owner}],
            "100",
        )
    assert store.records(a, "gmail") == [{"id": "same-id", "subject": a}]
    assert store.records(b, "gmail") == [{"id": "same-id", "subject": b}]
    interrupted = store.begin_sync(a, "gmail")
    assert store.status(a, "gmail")["syncing"] is True
    assert store.abort_sync(a, "gmail", "wrong-owner", interrupted["revision"]) is False
    assert store.abort_sync(a, "gmail", interrupted["owner"], interrupted["revision"]) is True
    assert store.status(a, "gmail")["syncing"] is False
    assert store.records(a, "gmail") == [{"id": "same-id", "subject": a}]
    old = store.begin_sync(a, "gmail")
    with pytest.raises(RuntimeError):
        store.begin_sync(a, "gmail")
    store.configure(a, "gmail", {"refresh_token": "replacement-fixture"})
    with pytest.raises(RuntimeError):
        store.commit_sync(a, "gmail", old["owner"], old["revision"], [{"id": "stale"}], "200")
    assert store.records(a, "gmail") == []
    assert store.records(b, "gmail") == [{"id": "same-id", "subject": b}]
    with Session(engine) as db:
        ca = db.get(AccountProvider, (a, "gmail"))
        cb = db.get(AccountProvider, (b, "gmail"))
        assert b"replacement-fixture" not in ca.credentials
        ca.credentials = cb.credentials
        db.commit()
    with pytest.raises(PermissionError):
        store.begin_sync(a, "gmail")
    store.configure(a, "gmail", {})
    with pytest.raises(ValueError):
        store.begin_sync(a, "gmail")
    assert store.records(b, "gmail") == [{"id": "same-id", "subject": b}]
