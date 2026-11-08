from multiprocessing import get_context

import pytest
from lifeos.account_archive import MAGIC, AccountArchive
from lifeos.account_partial_inventory import AccountPartialInventory
from lifeos.account_records import AccountRecords
from lifeos.accounts import AccountService


def _backup_until_flush(directory, owner, pipe):
    from lifeos import account_archive
    from lifeos.main import create_app

    engine = create_app().state.assistant.engine
    original_fsync = account_archive.os.fsync

    def pause_fsync(fd):
        pipe.send("encrypted_partial_flushed")
        if not pipe.poll(30):
            raise RuntimeError("Fixture parent did not terminate writer")
        return original_fsync(fd)

    account_archive.os.fsync = pause_fsync
    try:
        AccountArchive(engine, directory).create(owner, "fixture archive password")
    except Exception as error:
        pipe.send({"error": type(error).__name__, "detail": str(error)})
        raise
    finally:
        account_archive.os.fsync = original_fsync
        engine.dispose()
        pipe.close()


def test_killed_backup_partial_is_hidden_and_next_backup_is_usable(client, setup_app):
    engine, directory = setup_app[0].state.assistant.engine, setup_app[1]
    owner = AccountService(engine, enabled=True).register("backup-kill-fixture", "fixture password")
    AccountRecords(engine).save(owner, "tasks", {"title": "Synthetic private task"})
    archive = AccountArchive(engine, directory)
    context = get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=_backup_until_flush, args=(directory, owner, child))
    process.start()
    child.close()
    try:
        assert parent.poll(15), "Writer did not reach its encrypted partial file"
        assert parent.recv() == "encrypted_partial_flushed"
        with pytest.raises(RuntimeError, match="account_storage_busy"):
            AccountPartialInventory(engine, directory).inspect(owner)
        process.terminate()
        process.join(10)
        assert not process.is_alive() and process.exitcode != 0
        partials = list(archive.folder(owner).glob("*.partial"))
        assert len(partials) == 1
        assert partials[0].read_bytes().startswith(MAGIC)
        assert b"Synthetic private task" not in partials[0].read_bytes()
        assert archive.list(owner) == []
        saved = archive.create(owner, "fixture archive password")
        assert [row["id"] for row in archive.list(owner)] == [saved["id"]]
        assert archive.read(owner, saved["id"], "fixture archive password")["tables"]["tasks"][0]["title"] == "Synthetic private task"
        # Observed limitation: a killed process cannot run its finally cleanup.
        assert partials[0].exists()
        inventory = AccountPartialInventory(engine, directory).inspect(owner)
        assert [row["name"] for row in inventory["partials"]] == [partials[0].name]
        assert inventory["deletion_authorized"] is False
    finally:
        parent.close()
        if process.is_alive():
            process.terminate()
        process.join(10)
