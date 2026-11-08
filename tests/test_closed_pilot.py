from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from lifeos.deployment import DeploymentConfig


def test_pilot_configuration_is_canonical_and_server_only(tmp_path):
    owner = str(uuid4())
    env = {
        "LIFEOS_DEPLOYMENT_MODE": "server",
        "LIFEOS_PUBLIC_ORIGIN": "https://lifeos.example",
        "LIFEOS_DATA_DIR": str(tmp_path),
        "LIFEOS_TEST_MODE": "1",
        "LIFEOS_PILOT_OWNER_ID": owner,
    }
    config = DeploymentConfig.from_env(env)
    assert config.pilot_owner_id == owner
    assert config.allows_account(owner) and not config.allows_account(str(uuid4()))
    for invalid in ("not-uuid", owner.upper()):
        with pytest.raises(ValueError):
            DeploymentConfig.from_env({**env, "LIFEOS_PILOT_OWNER_ID": invalid})
    with pytest.raises(ValueError):
        DeploymentConfig.from_env({"LIFEOS_PILOT_OWNER_ID": owner})


def test_closed_pilot_blocks_signup_other_login_and_existing_cookie(setup_app, monkeypatch):
    monkeypatch.setenv("LIFEOS_ACCOUNT_MODE", "1")
    headers = {"X-LifeOS-Key": "test-process-key"}
    with TestClient(setup_app[2](), base_url="https://127.0.0.1:8000", headers=headers) as web:
        for login in ("pilot-owner", "pilot-other"):
            assert (
                web.post(
                    "/accounts/register", json={"login": login, "password": "fixture password"}
                ).status_code
                == 201
            )
        first = web.post(
            "/accounts/session", json={"login": "pilot-owner", "password": "fixture password"}
        ).json()
        web.post("/accounts/session", json={"login": "pilot-other", "password": "fixture password"})
        other_cookie = web.cookies.get("lifeos_session")
    monkeypatch.setenv("LIFEOS_DEPLOYMENT_MODE", "server")
    monkeypatch.setenv("LIFEOS_PUBLIC_ORIGIN", "https://lifeos.example")
    monkeypatch.setenv("LIFEOS_TEST_MODE", "1")
    monkeypatch.setenv("LIFEOS_PILOT_OWNER_ID", first["account_id"])
    with TestClient(
        setup_app[2](),
        base_url="https://127.0.0.1:8000",
        headers={**headers, "Origin": "https://lifeos.example"},
    ) as web:
        assert web.get("/mode").json()["registration_open"] is False
        assert (
            web.post(
                "/accounts/register", json={"login": "new-user", "password": "fixture password"}
            ).status_code
            == 403
        )
        assert (
            web.post(
                "/accounts/session", json={"login": "pilot-other", "password": "fixture password"}
            ).status_code
            == 401
        )
        web.cookies.set("lifeos_session", other_cookie, domain="127.0.0.1", path="/")
        assert web.get("/accounts/workspace/tasks").status_code in (401, 403)
        assert (
            web.post(
                "/accounts/session", json={"login": "pilot-owner", "password": "fixture password"}
            ).status_code
            == 200
        )
        assert web.get("/accounts/workspace/tasks").status_code == 200


def test_pilot_provisioning_is_empty_only_and_survives_deletion_marker(tmp_path, monkeypatch):
    from lifeos.accounts import AccountService
    from lifeos.db import migrate, open_database
    from lifeos.models import Account
    from lifeos.pilot_setup import provision_owner
    from sqlalchemy.orm import Session

    owner = str(uuid4())
    monkeypatch.setenv("LIFEOS_DEPLOYMENT_MODE", "server")
    monkeypatch.setenv("LIFEOS_PUBLIC_ORIGIN", "https://lifeos.example")
    monkeypatch.setenv("LIFEOS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIFEOS_TEST_MODE", "1")
    monkeypatch.setenv("LIFEOS_PILOT_OWNER_ID", owner)
    engine = open_database(tmp_path)
    migrate(engine)
    try:
        assert provision_owner("pilot-owner", "fixture password") == {"owner_created": True}
        auth = AccountService(engine, enabled=True)
        assert auth.login("pilot-owner", "fixture password")["account_id"] == owner
        with pytest.raises(ValueError):
            provision_owner("replacement", "another password")
        with Session(engine) as db:
            db.query(__import__("lifeos.models", fromlist=["LoginSession"]).LoginSession).delete()
            db.delete(db.get(Account, owner))
            db.commit()
        with pytest.raises(ValueError):
            provision_owner("replacement", "another password")
    finally:
        engine.dispose()


def test_pilot_missing_owner_refuses_startup(setup_app, monkeypatch):
    monkeypatch.setenv("LIFEOS_DEPLOYMENT_MODE", "server")
    monkeypatch.setenv("LIFEOS_PUBLIC_ORIGIN", "https://lifeos.example")
    monkeypatch.setenv("LIFEOS_TEST_MODE", "1")
    monkeypatch.setenv("LIFEOS_PILOT_OWNER_ID", str(uuid4()))
    with pytest.raises(RuntimeError, match="pilot owner unavailable"):
        with TestClient(setup_app[2]()):
            pass


def test_pilot_background_and_recovery_ignore_other_owner(setup_app, monkeypatch):
    from lifeos.account_lifecycle import AccountLifecycleService
    from lifeos.account_operations import AccountOperations
    from lifeos.account_providers import AccountProviders
    from lifeos.account_worker import AccountSyncWorker
    from lifeos.accounts import AccountService
    from lifeos.db import migrate
    from lifeos.models import AccountPreference
    from sqlalchemy.orm import Session

    engine = setup_app[0].state.assistant.engine
    migrate(engine)
    auth = AccountService(engine, enabled=True)
    owners = [
        auth.register(name, "fixture password") for name in ("background-owner", "background-other")
    ]
    signed = auth.login("background-other", "fixture password")
    lifecycle = AccountLifecycleService(auth, setup_app[1])
    other_key = lifecycle.generate_key(owners[1], signed["token"], "fixture password")[
        "recovery_key"
    ]
    providers = AccountProviders(engine, setup_app[1])
    for owner in owners:
        providers.configure(owner, "google", {"refresh_token": "synthetic refresh token"})
        with Session(engine) as db:
            for kind in ("briefings", "backup_schedule"):
                db.add(AccountPreference(account_id=owner, kind=kind, payload="{}", revision=0))
            db.commit()
    monkeypatch.setenv("LIFEOS_DEPLOYMENT_MODE", "server")
    monkeypatch.setenv("LIFEOS_PUBLIC_ORIGIN", "https://lifeos.example")
    monkeypatch.setenv("LIFEOS_TEST_MODE", "1")
    monkeypatch.setenv("LIFEOS_PILOT_OWNER_ID", owners[0])
    assert AccountSyncWorker(engine, setup_app[1]).due() == [(owners[0], "google")]
    assert AccountOperations(engine, setup_app[1]).owners("briefings") == [owners[0]]
    assert AccountOperations(engine, setup_app[1]).owners("backup") == [owners[0]]
    assert not lifecycle.recover("background-other", other_key, "replacement password")
    with pytest.raises(PermissionError):
        providers.status(owners[1], "google")
    from lifeos.account_archive import AccountArchive
    from lifeos.account_records import AccountRecords
    from lifeos.account_restore import AccountRestore

    records = AccountRecords(engine)
    task = records.save(owners[0], "tasks", {"title": "Original pilot task"})
    archive = AccountArchive(engine, setup_app[1]).create(owners[0], "fixture backup password")
    records.save(owners[0], "tasks", {"title": "Changed pilot task"}, task["id"])
    owner_session = auth.login("background-owner", "fixture password")
    restore = AccountRestore(engine, setup_app[1])
    preview = restore.preview(
        owners[0], owner_session["token"], archive["id"], "fixture backup password"
    )
    assert restore.confirm(
        owners[0], owner_session["token"], preview["id"], "fixture backup password"
    )["restored"]
    assert records.list(owners[0], "tasks")[0]["title"] == "Original pilot task"
