import sqlite3

import pytest


@pytest.mark.parametrize("failure", [OSError, KeyboardInterrupt])
def test_restore_failure_rolls_back_and_keeps_safety_backup(
    client, setup_app, tmp_path, monkeypatch, failure
):
    from cryptography.fernet import Fernet
    from lifeos import recovery
    from lifeos.db import migrate, open_database
    from lifeos.security import initialize_password

    (setup_app[1] / "provider.key").write_bytes(Fernet.generate_key())

    source = client.post("/recovery/backups", json={"password": "backup fixture password"}).json()
    path = setup_app[1] / "backups" / (source["id"] + ".lifeosbackup")
    target = tmp_path / "rollback-target"
    initialize_password(target, "different target fixture password")
    engine = open_database(target)
    migrate(engine)
    engine.dispose()
    with sqlite3.connect(target / "lifeos.sqlite3") as db:
        db.execute(
            "insert into tasks(id,title,notes,priority,completed,created_at) values('existing','Keep me','','high',0,'2026-10-26')"
        )
    original_auth = (target / "auth.json").read_bytes()
    original_key = Fernet.generate_key()
    (target / "provider.key").write_bytes(original_key)
    write = recovery.atomic_write
    failed = False

    def fail_once(file, data):
        nonlocal failed
        if file.name == "provider.key" and not failed:
            failed = True
            raise failure("synthetic write failure")
        write(file, data)

    monkeypatch.setattr(recovery, "atomic_write", fail_once)
    with pytest.raises((recovery.RecoveryError, KeyboardInterrupt)):
        recovery.restore_backup(path, "backup fixture password", target)
    assert (target / "auth.json").read_bytes() == original_auth
    assert (target / "provider.key").read_bytes() == original_key
    with sqlite3.connect(target / "lifeos.sqlite3") as db:
        assert db.execute("select title from tasks").fetchone()[0] == "Keep me"
    assert len(list((target / "backups").glob("*.lifeosbackup"))) == 1
    assert not (target / ".restore-in-progress").exists()


@pytest.mark.parametrize("attack", ["path", "schema"])
def test_authenticated_but_unsafe_archive_is_rejected(client, setup_app, tmp_path, attack):
    import io
    import os
    import zipfile

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from lifeos import recovery

    password = "backup fixture password"
    created = client.post("/recovery/backups", json={"password": password}).json()
    path = setup_app[1] / "backups" / (created["id"] + ".lifeosbackup")
    entries, _ = recovery.unpack_backup(path, password)
    if attack == "path":
        entries["../escape"] = b"never extract"
    else:
        database = tmp_path / "modified.sqlite3"
        database.write_bytes(entries["lifeos.sqlite3"])
        with sqlite3.connect(database) as db:
            db.execute("create view injected_view as select 'unexpected'")
        entries["lifeos.sqlite3"] = database.read_bytes()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    salt, nonce = os.urandom(16), os.urandom(12)
    header = recovery.MAGIC + salt + nonce
    modified = tmp_path / (attack + ".lifeosbackup")
    modified.write_bytes(
        header + AESGCM(recovery.derive(password, salt)).encrypt(nonce, buffer.getvalue(), header)
    )
    with pytest.raises(recovery.RecoveryError):
        recovery.inspect_backup(modified, password)
    assert not (tmp_path / "escape").exists()
