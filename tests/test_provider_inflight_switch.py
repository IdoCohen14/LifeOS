from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from lifeos.account_providers import AccountProviders
from lifeos.accounts import AccountService
from lifeos.db import open_database


def _late_sync_process(directory, owner, pipe):
    # A fresh interpreter needs the full mapped table registry, not fixture engines.
    import lifeos.main  # noqa: F401

    engine = open_database(directory)
    try:
        store = AccountProviders(engine, directory)
        lease = store.begin_sync(owner, "google")
        pipe.send("ready")
        if not pipe.poll(15) or pipe.recv() != "release":
            raise RuntimeError("Fixture parent did not release worker")
        try:
            store.commit_sync(owner, "google", lease["owner"], lease["revision"], [{"id": "late-process"}])
        except RuntimeError:
            rejected = True
        else:
            rejected = False
        aborted = store.abort_sync(owner, "google", lease["owner"], lease["revision"], error="late-process-error")
        pipe.send({"rejected": rejected, "aborted": aborted})
    finally:
        engine.dispose()
        pipe.close()


def test_separate_process_late_sync_cannot_overwrite_new_connection(client, setup_app):
    from multiprocessing import get_context

    engine, directory = setup_app[0].state.assistant.engine, setup_app[1]
    owner = AccountService(engine, enabled=True).register("process-sync", "fixture password")
    store = AccountProviders(engine, directory)
    store.configure(owner, "google", {"refresh_token": "original-process-fixture"})
    context = get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=_late_sync_process, args=(directory, owner, child))
    process.start()
    child.close()
    try:
        assert parent.poll(15), "Child did not acquire its lease"
        assert parent.recv() == "ready"
        store.configure(owner, "google", {"refresh_token": "new-process-fixture"})
        fresh = store.begin_sync(owner, "google")
        store.commit_sync(owner, "google", fresh["owner"], fresh["revision"], [{"id": "fresh-process"}])
        parent.send("release")
        assert parent.poll(15), "Child did not finish"
        assert parent.recv() == {"rejected": True, "aborted": False}
        process.join(10)
        assert process.exitcode == 0
        assert store.records(owner, "google") == [{"id": "fresh-process"}]
        assert store.status(owner, "google")["error"] is None
        lease = store.begin_sync(owner, "google")
        assert lease["credentials"] == {"refresh_token": "new-process-fixture"}
        store.abort_sync(owner, "google", lease["owner"], lease["revision"])
    finally:
        parent.close()
        if process.is_alive():
            process.terminate()
        process.join(10)


@pytest.mark.parametrize("reconnect", [False, True])
def test_late_sync_cannot_restore_disconnected_or_replace_reconnected_source(
    client, setup_app, reconnect
):
    engine, directory = setup_app[0].state.assistant.engine, setup_app[1]
    accounts = AccountService(engine, enabled=True)
    owner = accounts.register("inflight-owner", "fixture password")
    other = accounts.register("inflight-other", "fixture password")
    store = AccountProviders(engine, directory)
    for account in (owner, other):
        store.configure(account, "google", {"refresh_token": "old-fixture"})
        lease = store.begin_sync(account, "google")
        store.commit_sync(account, "google", lease["owner"], lease["revision"], [{"id": "old"}])
    worker_engine = open_database(directory)
    ready, release = Event(), Event()

    def delayed_sync():
        worker = AccountProviders(worker_engine, directory)
        lease = worker.begin_sync(owner, "google")
        ready.set()
        assert release.wait(10), "Fixture synchronization timed out"
        with pytest.raises(RuntimeError, match="ownership lost"):
            worker.commit_sync(owner, "google", lease["owner"], lease["revision"], [{"id": "late"}])
        return worker.abort_sync(owner, "google", lease["owner"], lease["revision"], error="late_error")

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(delayed_sync)
            try:
                assert ready.wait(10), "Worker never acquired its lease"
                store.configure(owner, "google", {"refresh_token": "new-fixture"} if reconnect else {})
                if reconnect:
                    fresh = store.begin_sync(owner, "google")
                    store.commit_sync(owner, "google", fresh["owner"], fresh["revision"], [{"id": "fresh"}])
            finally:
                release.set()
            assert result.result(timeout=10) is False
        assert store.records(owner, "google") == ([{"id": "fresh"}] if reconnect else [])
        assert store.status(owner, "google")["error"] is None
        assert store.status(owner, "google")["syncing"] is False
        assert store.records(other, "google") == [{"id": "old"}]
        if reconnect:
            next_lease = store.begin_sync(owner, "google")
            assert next_lease["credentials"] == {"refresh_token": "new-fixture"}
            store.abort_sync(owner, "google", next_lease["owner"], next_lease["revision"])
        else:
            with pytest.raises(ValueError, match="not configured"):
                store.begin_sync(owner, "google")
    finally:
        worker_engine.dispose()
