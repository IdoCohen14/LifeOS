import json
from multiprocessing import get_context

from lifeos.account_archive import AccountArchive
from lifeos.account_records import AccountRecords
from lifeos.account_restore import AccountRestore
from lifeos.accounts import AccountService
from lifeos.db import open_database


def _restore_until_write(directory, owner, token, preview_id, pipe):
    from lifeos.main import create_app
    from sqlalchemy import event

    # Construct the same model registry as the actual API before reading archives.
    engine = create_app().state.assistant.engine

    def pause_before_insert(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO tasks"):
            pipe.send("deletes_executed_before_insert")
            if not pipe.poll(30):
                raise RuntimeError("Fixture parent did not terminate child")
            raise RuntimeError("Fixture resumed unexpectedly")

    event.listen(engine, "before_cursor_execute", pause_before_insert)
    try:
        AccountRestore(engine, directory).confirm(owner, token, preview_id, "fixture archive password")
    except Exception as error:
        pipe.send({"error": type(error).__name__, "detail": str(error)})
        raise
    finally:
        engine.dispose()
        pipe.close()


def test_killed_restore_process_rolls_back_database_and_keeps_safety_archive(client, setup_app):
    engine, directory = setup_app[0].state.assistant.engine, setup_app[1]
    accounts = AccountService(engine, enabled=True)
    owner = accounts.register("kill-restore-fixture", "fixture password")
    token = accounts.login("kill-restore-fixture", "fixture password")["token"]
    records = AccountRecords(engine)
    task = records.save(owner, "tasks", {"title": "Archived fixture"})
    archive = AccountRestore(engine, directory)
    original = archive.create(owner, "fixture archive password")
    records.save(owner, "tasks", {"title": "Current fixture", "notes": "Must survive termination"}, task["id"])
    before = json.loads(archive.export(owner))["tables"]
    preview = archive.preview(owner, token, original["id"], "fixture archive password")
    context = get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=_restore_until_write, args=(directory, owner, token, preview["id"], child))
    process.start()
    child.close()
    try:
        assert parent.poll(15), "Restore child did not reach the write transaction"
        assert parent.recv() == "deletes_executed_before_insert"
        process.terminate()
        process.join(10)
        assert not process.is_alive() and process.exitcode != 0
        reopened = open_database(directory)
        try:
            recovered = AccountArchive(reopened, directory)
            assert json.loads(recovered.export(owner))["tables"] == before
            backups = recovered.list(owner)
            assert len(backups) == 2
            safety = next(row for row in backups if row["id"] != original["id"])
            assert recovered.read(owner, safety["id"], "fixture archive password")["tables"] == before
            assert not list(recovered.folder(owner).glob("*.partial"))
            # The account and its original password remain usable after rollback.
            assert AccountService(reopened, enabled=True).login("kill-restore-fixture", "fixture password")["token"]
        finally:
            reopened.dispose()
    finally:
        parent.close()
        if process.is_alive():
            process.terminate()
        process.join(10)
