import os
import time
from uuid import uuid4

import pytest
from lifeos.account_archive import AccountArchive
from lifeos.account_partial_inventory import AccountPartialInventory
from lifeos.accounts import AccountService
from lifeos.data_lock import account_storage_lock


def test_inventory_is_bounded_metadata_only_and_preserves_files(client, setup_app):
    app, directory, _ = setup_app
    engine = app.state.assistant.engine
    owner = AccountService(engine, enabled=True).register("partial-fixture", "fixture password")
    folder = AccountArchive(engine, directory).folder(owner)
    folder.mkdir(parents=True)
    old = folder / f"{uuid4()}.partial"
    old.write_bytes(b"arbitrary bytes; validity must not be inferred")
    os.utime(old, (time.time() - 172800,) * 2)
    young = folder / f"{uuid4()}.partial"
    young.write_bytes(b"new")
    future = folder / f"{uuid4()}.partial"
    future.write_bytes(b"future timestamp")
    os.utime(future, (time.time() + 172800,) * 2)
    (folder / "unknown.partial").write_bytes(b"unknown")
    (folder / f"{uuid4()}.lifeosaccountbackup").write_bytes(b"completed")
    (folder / f"{uuid4()}.partial").mkdir()
    foreign = folder.parent / str(uuid4())
    foreign.mkdir()
    (foreign / f"{uuid4()}.partial").write_bytes(b"other owner")
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir() if p.is_file()}
    result = AccountPartialInventory(engine, directory).inspect(owner)
    assert result["deletion_authorized"] is False
    assert result["contents_verified"] is False
    assert result["truncated"] is False
    rows = {r["name"]: r for r in result["partials"]}
    assert set(rows) == {old.name, young.name, future.name}
    assert rows[old.name]["older_than_24h"] is True
    assert rows[young.name]["older_than_24h"] is False
    assert rows[future.name]["future_timestamp"] is True
    assert rows[future.name]["older_than_24h"] is False
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before}
    bounded = AccountPartialInventory(engine, directory).inspect(owner, max_entries=1)
    assert bounded["truncated"] is True
    assert bounded["scanned"] == 1
    with pytest.raises(ValueError):
        AccountPartialInventory(engine, directory).inspect(owner, max_entries=10001)


def test_inventory_respects_storage_lock_and_account_authorization(client, setup_app):
    app, directory, _ = setup_app
    engine = app.state.assistant.engine
    owner = AccountService(engine, enabled=True).register("partial-lock", "fixture password")
    inventory = AccountPartialInventory(engine, directory)
    with account_storage_lock(directory, owner):
        with pytest.raises(RuntimeError, match="account_storage_busy"):
            inventory.inspect(owner)
    assert inventory.inspect(owner)["partials"] == []
    with pytest.raises(PermissionError):
        inventory.inspect(str(uuid4()))
    (directory / ".restore-in-progress").write_text("fixture recovery fence")
    with pytest.raises(RuntimeError, match="complete_recovery_before_starting_lifeos"):
        inventory.inspect(owner)


def test_inventory_excludes_hard_links(client, setup_app):
    app, directory, _ = setup_app
    engine = app.state.assistant.engine
    owner = AccountService(engine, enabled=True).register("partial-link", "fixture password")
    folder = AccountArchive(engine, directory).folder(owner)
    folder.mkdir(parents=True)
    target = directory / "fixture-content"
    target.write_bytes(b"not an archive")
    os.link(target, folder / f"{uuid4()}.partial")
    assert AccountPartialInventory(engine, directory).inspect(owner)["partials"] == []


@pytest.mark.skipif(os.name != "nt", reason="Native Windows junction behavior")
def test_inventory_excludes_windows_junction_without_following_or_removing_target(client, setup_app):
    import _winapi
    from pathlib import Path
    from tempfile import TemporaryDirectory

    app, _, _ = setup_app
    runtime = Path(__file__).resolve().parents[1] / ".runtime"
    engine = app.state.assistant.engine
    owner = AccountService(engine, enabled=True).register("partial-junction", "fixture password")
    runtime.mkdir(exist_ok=True)
    with TemporaryDirectory(dir=runtime, prefix="junction-inventory-") as base:
        directory = Path(base).resolve()
        assert directory.is_relative_to(runtime.resolve())
        folder = AccountArchive(engine, directory).folder(owner)
        folder.mkdir(parents=True)
        target = directory / "junction-target-fixture"
        target.mkdir()
        retained = target / "retained-fixture.txt"
        retained.write_bytes(b"fixture target remains untouched")
        link = folder / f"{uuid4()}.partial"
        _winapi.CreateJunction(str(target), str(link))
        try:
            result = AccountPartialInventory(engine, directory).inspect(owner)
            assert result["scanned"] == 1
            assert result["partials"] == []
            assert result["deletion_authorized"] is False
            assert retained.read_bytes() == b"fixture target remains untouched"
        finally:
            # Remove only the junction itself, never recursively traverse its target.
            os.rmdir(link)
        assert retained.read_bytes() == b"fixture target remains untouched"
