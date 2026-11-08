import pytest
from lifeos.accounts import AccountService
from lifeos.db import migrate, open_database
from lifeos.models import Account, AccountLifecycle
from sqlalchemy import text
from sqlalchemy.orm import Session


def test_reviewed_owner_deletion_preserves_other_account_and_removes_archives(tmp_path):
    from lifeos.account_lifecycle import AccountLifecycleService
    from lifeos.account_records import AccountRecords

    engine = open_database(tmp_path)
    migrate(engine)
    auth = AccountService(engine, enabled=True)
    service = AccountLifecycleService(auth, tmp_path)
    a = auth.register("delete-a", "fixture password")
    b = auth.register("delete-b", "fixture password")
    sa, sb = auth.login("delete-a", "fixture password"), auth.login("delete-b", "fixture password")
    records = AccountRecords(engine)
    records.save(a, "tasks", {"title": "A private fixture"})
    records.save(b, "tasks", {"title": "B retained fixture"})
    folder = tmp_path / "account-backups" / a
    folder.mkdir(parents=True)
    (folder / "fixture.lifeosaccountbackup").write_bytes(b"synthetic encrypted fixture")
    try:
        preview = service.deletion_preview(a, sa["token"])
        with pytest.raises(PermissionError):
            service.confirm_deletion(a, sb["token"], preview["id"], "fixture password", "delete-a")
        with pytest.raises(PermissionError):
            service.confirm_deletion(a, sa["token"], preview["id"], "wrong password", "delete-a")
        assert service.confirm_deletion(
            a, sa["token"], preview["id"], "fixture password", "delete-a"
        )["deleted"]
        with Session(engine) as db:
            assert db.get(Account, a) is None
            assert db.get(AccountLifecycle, a) is None
            assert db.get(Account, b).enabled
            assert db.execute(text("pragma foreign_key_check")).all() == []
        assert not folder.exists()
        assert records.list(b, "tasks")[0]["title"] == "B retained fixture"
    finally:
        engine.dispose()


def test_cleanup_failure_keeps_account_disabled_and_can_resume(tmp_path, monkeypatch):
    from lifeos.account_lifecycle import AccountLifecycleService

    engine = open_database(tmp_path)
    migrate(engine)
    auth = AccountService(engine, enabled=True)
    service = AccountLifecycleService(auth, tmp_path)
    account = auth.register("delete-failure", "fixture password")
    signed = auth.login("delete-failure", "fixture password")
    preview = service.deletion_preview(account, signed["token"])
    real = service.cleanup_archives
    monkeypatch.setattr(
        service, "cleanup_archives", lambda owner: (_ for _ in ()).throw(OSError("fixture failure"))
    )
    try:
        result = service.confirm_deletion(
            account, signed["token"], preview["id"], "fixture password", "delete-failure"
        )
        assert not result["deleted"] and result["cleanup_pending"]
        with Session(engine) as db:
            assert not db.get(Account, account).enabled
            assert db.get(AccountLifecycle, account).deletion_state == "cleanup_pending"
        assert auth.login("delete-failure", "fixture password") is None
        monkeypatch.setattr(service, "cleanup_archives", real)
        assert service.finish_deletion(account)["deleted"]
        with Session(engine) as db:
            assert db.get(Account, account) is None
    finally:
        engine.dispose()


def test_deletion_routes_require_review_and_csrf(setup_app, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("LIFEOS_ACCOUNT_MODE", "1")
    with TestClient(
        setup_app[2](),
        base_url="http://127.0.0.1:8000",
        headers={"X-LifeOS-Key": "test-process-key"},
    ) as web:
        body = {"login": "delete-route", "password": "fixture password"}
        assert web.post("/accounts/register", json=body).status_code == 201
        session = web.post("/accounts/session", json=body).json()
        assert web.post("/accounts/deletion/preview").status_code == 403
        web.headers["X-CSRF-Token"] = session["csrf"]
        preview = web.post("/accounts/deletion/preview").json()
        response = web.post(
            "/accounts/deletion/confirm",
            json={
                "preview_id": preview["id"],
                "login": body["login"],
                "password": "wrong password",
            },
        )
        assert response.status_code == 403
        response = web.post(
            "/accounts/deletion/confirm", json={"preview_id": preview["id"], **body}
        )
        assert response.status_code == 200 and response.json()["deleted"]
        assert web.get("/accounts/session").status_code == 401


def test_expired_review_and_archive_lock_require_safe_retry(tmp_path):
    import json

    from lifeos.account_lifecycle import AccountLifecycleService
    from lifeos.data_lock import account_storage_lock

    engine = open_database(tmp_path)
    migrate(engine)
    auth = AccountService(engine, enabled=True)
    service = AccountLifecycleService(auth, tmp_path)
    owner = auth.register("archive-lock-delete", "fixture password")
    signed = auth.login("archive-lock-delete", "fixture password")
    try:
        preview = service.deletion_preview(owner, signed["token"])
        with Session(engine) as db:
            row = db.get(AccountLifecycle, owner)
            value = json.loads(row.deletion_preview)
            value["expires"] = 0
            row.deletion_preview = json.dumps(value)
            db.commit()
        with pytest.raises(ValueError, match="expired"):
            service.confirm_deletion(
                owner, signed["token"], preview["id"], "fixture password", "archive-lock-delete"
            )
        preview = service.deletion_preview(owner, signed["token"])
        with account_storage_lock(tmp_path, owner):
            pending = service.confirm_deletion(
                owner, signed["token"], preview["id"], "fixture password", "archive-lock-delete"
            )
            assert pending == {"deleted": False, "cleanup_pending": True}
        assert service.finish_deletion(owner)["deleted"]
    finally:
        engine.dispose()


def test_offline_retry_script_requires_an_already_confirmed_disabled_account(tmp_path, monkeypatch):
    import json
    import subprocess
    import sys

    from lifeos.account_lifecycle import AccountLifecycleService
    from lifeos.db import ROOT

    engine = open_database(tmp_path)
    migrate(engine)
    auth = AccountService(engine, enabled=True)
    service = AccountLifecycleService(auth, tmp_path)
    owner = auth.register("offline-delete", "fixture password")
    signed = auth.login("offline-delete", "fixture password")
    preview = service.deletion_preview(owner, signed["token"])
    monkeypatch.setattr(
        service, "cleanup_archives", lambda _: (_ for _ in ()).throw(OSError("fixture"))
    )
    try:
        assert service.confirm_deletion(
            owner, signed["token"], preview["id"], "fixture password", "offline-delete"
        )["cleanup_pending"]
    finally:
        engine.dispose()
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/finish_account_deletion.py"),
            "--data-dir",
            str(tmp_path),
            "--account-id",
            owner,
            "--confirm",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["deleted"]
