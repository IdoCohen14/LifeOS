from lifeos.account_providers import AccountProviders
from lifeos.account_worker import AccountSyncWorker
from lifeos.accounts import AccountService
from lifeos.models import Account, AccountProvider
from sqlalchemy.orm import Session


def test_account_worker_skips_incomplete_disabled_busy_and_not_due(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    a = auth.register("worker-a", "fixture password a")
    b = auth.register("worker-b", "fixture password b")
    storage = AccountProviders(engine, setup_app[1])
    storage.configure(a, "gmail", {"refresh_token": "synthetic"})
    storage.configure(a, "google", {"client_id": "fixture", "client_secret": "synthetic"})
    storage.configure(b, "gmail", {"refresh_token": "synthetic"})
    with Session(engine) as db:
        db.get(Account, b).enabled = False
        db.commit()
    calls = []

    class Adapter:
        def sync(self, owner):
            calls.append(owner)
            lease = storage.begin_sync(owner, "gmail")
            storage.abort_sync(
                owner, "gmail", lease["owner"], lease["revision"], error="provider_unavailable"
            )
            raise RuntimeError("Synthetic failure")

    worker = AccountSyncWorker(engine, setup_app[1], adapters={"gmail": Adapter()})
    assert worker.due() == [(a, "gmail")]
    assert worker.tick() == {"completed": 0, "failed": 1}
    assert calls == [a]
    assert worker.due() == []
    with Session(engine) as db:
        db.get(Account, b).enabled = True
        db.get(AccountProvider, (b, "gmail")).lease_until = 9999999999
        db.commit()
    assert worker.due() == []
