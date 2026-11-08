import json

import pytest
from lifeos.account_archive import AccountArchive
from lifeos.account_records import AccountRecords
from lifeos.accounts import AccountService


@pytest.mark.parametrize("source_change", ["valid_replacement", "truncated", "removed"])
def test_changed_archive_after_review_cannot_replace_current_data(client, setup_app, source_change):
    from lifeos.account_restore import AccountRestore
    from lifeos.models import LoginSession
    from sqlalchemy.orm import Session

    engine = setup_app[0].state.assistant.engine
    accounts = AccountService(engine, enabled=True)
    owner = accounts.register("changed-source-fixture", "fixture password")
    token = accounts.login("changed-source-fixture", "fixture password")["token"]
    store = AccountRecords(engine)
    task = store.save(owner, "tasks", {"title": "Reviewed archive"})
    restore = AccountRestore(engine, setup_app[1])
    saved = restore.create(owner, "fixture backup password")
    store.save(owner, "tasks", {"title": "Different archive"}, task["id"])
    replacement = restore.create(owner, "fixture backup password")
    store.save(owner, "tasks", {"title": "Current data"}, task["id"])
    before = json.loads(restore.export(owner))["tables"]
    preview = restore.preview(owner, token, saved["id"], "fixture backup password")
    with Session(engine) as db:
        sessions = db.query(LoginSession).filter_by(account_id=owner).count()
    path = restore.file(owner, saved["id"])
    replacement_path = restore.file(owner, replacement["id"])
    replacement_bytes = replacement_path.read_bytes()
    if source_change == "valid_replacement":
        path.write_bytes(replacement_bytes)
    elif source_change == "truncated":
        path.write_bytes(path.read_bytes()[:20])
    else:
        path.unlink()
    files_before = set(restore.folder(owner).iterdir())
    with pytest.raises((ValueError, LookupError)):
        restore.confirm(owner, token, preview["id"], "fixture backup password")
    assert json.loads(restore.export(owner))["tables"] == before
    assert replacement_path.read_bytes() == replacement_bytes
    assert set(restore.folder(owner).iterdir()) == files_before
    with Session(engine) as db:
        assert db.query(LoginSession).filter_by(account_id=owner).count() == sessions


@pytest.mark.parametrize("failure_sql", ["INSERT INTO tasks", "DELETE FROM sessions"])
def test_restore_transaction_failure_rolls_back_and_keeps_safety_backup(
    client, setup_app, failure_sql
):
    from lifeos.account_restore import AccountRestore
    from lifeos.models import AccountProvider, AccountProviderRecord, LoginSession
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    owner = auth.register("rollback-fixture", "fixture password")
    other = auth.register("rollback-other", "fixture password")
    token = auth.login("rollback-fixture", "fixture password")["token"]
    records = AccountRecords(engine)
    task = records.save(owner, "tasks", {"title": "Archived fixture"})
    records.save(other, "tasks", {"title": "Other fixture"})
    restore = AccountRestore(engine, setup_app[1])
    saved = restore.create(owner, "fixture backup password")
    records.save(owner, "tasks", {"title": "Current fixture"}, task["id"])
    with Session(engine) as db:
        db.add(AccountProvider(account_id=owner, provider="google", authorized=True))
        db.flush()
        db.add(AccountProviderRecord(account_id=owner, provider="google", external_id="fixture", payload="{}"))
        db.commit()
        sessions_before = db.query(LoginSession).filter_by(account_id=owner).count()
    before = restore.export(owner)
    preview = restore.preview(owner, token, saved["id"], "fixture backup password")
    reached = []

    def fail_in_transaction(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith(failure_sql):
            reached.append(statement)
            raise RuntimeError("Synthetic restore transaction failure")

    event.listen(engine, "before_cursor_execute", fail_in_transaction)
    try:
        with pytest.raises(RuntimeError, match="Synthetic restore transaction failure"):
            restore.confirm(owner, token, preview["id"], "fixture backup password")
    finally:
        event.remove(engine, "before_cursor_execute", fail_in_transaction)
    assert len(reached) == 1
    assert json.loads(restore.export(owner))["tables"] == json.loads(before)["tables"]
    assert records.list(other, "tasks")[0]["title"] == "Other fixture"
    with Session(engine) as db:
        assert db.get(AccountProvider, (owner, "google")).authorized is True
        assert db.get(AccountProviderRecord, (owner, "google", "fixture")) is not None
        assert db.query(LoginSession).filter_by(account_id=owner).count() == sessions_before
    backups = restore.list(owner)
    assert len(backups) == 2
    safety = next(row for row in backups if row["id"] != saved["id"])
    safety_tables = restore.read(owner, safety["id"], "fixture backup password")["tables"]
    assert safety_tables == json.loads(before)["tables"]


@pytest.mark.parametrize("failure_point", ["fsync", "replace"])
def test_failed_safety_backup_keeps_current_data_and_removes_partial(
    client, setup_app, monkeypatch, failure_point
):
    import errno

    from lifeos import account_archive
    from lifeos.account_restore import AccountRestore
    from lifeos.models import AccountProvider, LoginSession
    from sqlalchemy.orm import Session

    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    owner = auth.register("disk-failure-fixture", "fixture password")
    token = auth.login("disk-failure-fixture", "fixture password")["token"]
    records = AccountRecords(engine)
    task = records.save(owner, "tasks", {"title": "Archived fixture"})
    restore = AccountRestore(engine, setup_app[1])
    saved = restore.create(owner, "fixture backup password")
    archive_before = restore.file(owner, saved["id"]).read_bytes()
    records.save(owner, "tasks", {"title": "Current fixture"}, task["id"])
    with Session(engine) as db:
        db.add(AccountProvider(account_id=owner, provider="google", authorized=True))
        db.commit()
        sessions_before = db.query(LoginSession).filter_by(account_id=owner).count()
    preview = restore.preview(owner, token, saved["id"], "fixture backup password")

    def disk_failure(*args, **kwargs):
        raise OSError(errno.ENOSPC, "Synthetic fixture disk failure")

    with monkeypatch.context() as patch:
        patch.setattr(account_archive.os, failure_point, disk_failure)
        with pytest.raises(OSError, match="Synthetic fixture disk failure"):
            restore.confirm(owner, token, preview["id"], "fixture backup password")
    assert records.list(owner, "tasks")[0]["title"] == "Current fixture"
    assert [row["id"] for row in restore.list(owner)] == [saved["id"]]
    assert restore.file(owner, saved["id"]).read_bytes() == archive_before
    assert list(restore.folder(owner).glob("*.partial")) == []
    with Session(engine) as db:
        assert db.get(AccountProvider, (owner, "google")).authorized is True
        assert db.query(LoginSession).filter_by(account_id=owner).count() == sessions_before


@pytest.mark.parametrize("expire_during_safety_backup", [False, True])
def test_expired_restore_keeps_current_data_and_connections(
    client, setup_app, monkeypatch, expire_during_safety_backup
):
    from types import SimpleNamespace

    from lifeos import account_restore
    from lifeos.models import AccountProvider, LoginSession
    from sqlalchemy.orm import Session

    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    owner = auth.register("expiry-fixture", "fixture password")
    token = auth.login("expiry-fixture", "fixture password")["token"]
    records = AccountRecords(engine)
    task = records.save(owner, "tasks", {"title": "Archived fixture"})
    restore = account_restore.AccountRestore(engine, setup_app[1])
    saved = restore.create(owner, "fixture backup password")
    records.save(owner, "tasks", {"title": "Current fixture"}, task["id"])
    with Session(engine) as db:
        db.add(AccountProvider(account_id=owner, provider="google", authorized=True))
        db.commit()
        sessions_before = db.query(LoginSession).filter_by(account_id=owner).count()
    clock = [account_restore.time.time()]
    monkeypatch.setattr(
        account_restore, "time",
        SimpleNamespace(time=lambda: clock[0], monotonic=account_restore.time.monotonic),
    )
    preview = restore.preview(owner, token, saved["id"], "fixture backup password")
    backups_before = len(restore.list(owner))
    if expire_during_safety_backup:
        create = restore.create

        def create_then_expire(*args, **kwargs):
            result = create(*args, **kwargs)
            clock[0] += 601
            return result

        monkeypatch.setattr(restore, "create", create_then_expire)
    else:
        clock[0] += 601
    with pytest.raises(ValueError, match="expired|changed"):
        restore.confirm(owner, token, preview["id"], "fixture backup password")
    assert records.list(owner, "tasks")[0]["title"] == "Current fixture"
    assert len(restore.list(owner)) == backups_before + int(expire_during_safety_backup)
    with Session(engine) as db:
        assert db.get(AccountProvider, (owner, "google")).authorized is True
        assert db.query(LoginSession).filter_by(account_id=owner).count() == sessions_before


def test_account_archive_exports_and_encrypts_only_owned_rows(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    a = auth.register("archive-a", "fixture password a")
    b = auth.register("archive-b", "fixture password b")
    records = AccountRecords(engine)
    records.save(a, "tasks", {"title": "Owned export fixture"})
    records.save(b, "tasks", {"title": "Other account secret fixture"})
    client.post("/tasks", json={"title": "Legacy secret fixture"})
    archive = AccountArchive(engine, setup_app[1])
    raw = archive.export(a)
    assert b.encode() not in raw and b"Legacy secret" not in raw
    assert b"Other account secret" not in raw and b"password_digest" not in raw
    data = json.loads(raw)
    assert [row["title"] for row in data["tables"]["tasks"]] == ["Owned export fixture"]
    saved = archive.create(a, "fixture backup password")
    assert archive.list(b) == [] and archive.list(a)[0]["id"] == saved["id"]
    info = archive.inspect(a, saved["id"], "fixture backup password")
    assert info["counts"]["tasks"] == 1
    with pytest.raises(LookupError):
        archive.inspect(b, saved["id"], "fixture backup password")
    with pytest.raises(ValueError):
        archive.inspect(a, saved["id"], "incorrect password")
    with pytest.raises(ValueError):
        archive.inspect(a, "../unsafe", "fixture backup password")


def test_account_restore_requires_fresh_preview_and_preserves_other_account(client, setup_app):
    from lifeos.account_restore import AccountRestore

    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    a = auth.register("restore-a", "fixture password a")
    b = auth.register("restore-b", "fixture password b")
    token = auth.login("restore-a", "fixture password a")["token"]
    other = auth.login("restore-b", "fixture password b")["token"]
    records = AccountRecords(engine)
    original = records.save(a, "tasks", {"title": "Original", "completed": True})
    records.save(b, "tasks", {"title": "Keep other"})
    archive = AccountArchive(engine, setup_app[1])
    saved = archive.create(a, "fixture backup password")
    records.save(a, "tasks", {"title": "Changed"}, original["id"])
    restore = AccountRestore(engine, setup_app[1])
    preview = restore.preview(a, token, saved["id"], "fixture backup password")
    with pytest.raises(PermissionError):
        restore.confirm(a, other, preview["id"], "fixture backup password")
    records.save(a, "tasks", {"title": "Late update"}, original["id"])
    with pytest.raises(ValueError, match="changed"):
        restore.confirm(a, token, preview["id"], "fixture backup password")
    preview = restore.preview(a, token, saved["id"], "fixture backup password")
    result = restore.confirm(a, token, preview["id"], "fixture backup password")
    assert result["safety_backup_id"] and result["relogin_required"]
    assert records.list(a, "tasks")[0]["title"] == "Original"
    assert records.list(b, "tasks")[0]["title"] == "Keep other"
    with pytest.raises(PermissionError):
        restore.confirm(a, token, preview["id"], "fixture backup password")


def test_restore_retains_owned_academic_links_and_binary_documents(client, setup_app):
    from lifeos.academic_models import DocumentSection, StudyDocument
    from lifeos.account_academic import AccountAcademic
    from lifeos.account_restore import AccountRestore, validate_tables
    from sqlalchemy.orm import Session

    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    owner = auth.register("restore-academic", "fixture password")
    token = auth.login("restore-academic", "fixture password")["token"]
    store = AccountAcademic(engine)
    term = store.save_root(
        owner, "terms", {"name": "Term", "start_date": "2026-10-01", "end_date": "2027-01-31"}
    )
    course = store.save_root(owner, "courses", {"term_id": term["id"], "name": "Course"})
    item = store.save_child(
        owner,
        "items",
        {"course_id": course["id"], "title": "Assignment", "due": "2026-11-02", "completed": True},
    )
    with Session(engine) as db:
        db.add(
            StudyDocument(
                id="archive-doc",
                course_id=course["id"],
                filename="fixture.txt",
                content=b"private fixture",
                created_at="2026-10-30T00:00:00Z",
                text_status="ready",
            )
        )
        db.flush()
        db.add(
            DocumentSection(
                id="archive-section",
                document_id="archive-doc",
                reference="1",
                position=0,
                text="private fixture",
            )
        )
        db.commit()
    archive = AccountArchive(engine, setup_app[1])
    saved = archive.create(owner, "fixture backup password")
    forged = json.loads(archive.export(owner))["tables"]
    forged["academic_items"][0]["task_id"] = "foreign-task"
    with pytest.raises(ValueError, match="parent mismatch"):
        validate_tables(owner, forged)
    store.delete_academic(owner, "items", item["id"])
    restore = AccountRestore(engine, setup_app[1])
    preview = restore.preview(owner, token, saved["id"], "fixture backup password")
    restore.confirm(owner, token, preview["id"], "fixture backup password")
    assert store.list_children(owner, "items")[0]["completed"]
    with Session(engine) as db:
        assert db.get(StudyDocument, "archive-doc").content == b"private fixture"
        assert db.get(DocumentSection, "archive-section").text == "private fixture"
