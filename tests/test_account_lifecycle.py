import json

import pytest
from lifeos.accounts import AccountService
from lifeos.db import migrate, open_database
from lifeos.models import Account, LoginSession
from lifeos.security import token_hash
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_recovery_key_rotation_consumption_and_session_isolation(tmp_path):
    from lifeos.account_lifecycle import AccountLifecycleService

    engine = open_database(tmp_path)
    migrate(engine)
    auth = AccountService(engine, enabled=True)
    service = AccountLifecycleService(auth, tmp_path)
    first = auth.register("recover-one", "fixture password")
    second = auth.register("recover-two", "fixture password")
    session = auth.login("recover-one", "fixture password")
    other = auth.login("recover-two", "fixture password")
    try:
        with pytest.raises(PermissionError):
            service.generate_key(first, other["token"], "fixture password")
        with pytest.raises(PermissionError):
            service.generate_key(first, session["token"], "wrong password")
        key = service.generate_key(first, session["token"], "fixture password")["recovery_key"]
        assert not service.recover("recover-two", key, "new fixture password")
        replacement = service.generate_key(first, session["token"], "fixture password")[
            "recovery_key"
        ]
        assert not service.recover("recover-one", key, "new fixture password")
        assert service.recover("RECOVER-ONE", replacement, "new fixture password")
        assert not service.recover("recover-one", replacement, "another password")
        assert auth.login("recover-one", "fixture password") is None
        assert auth.login("recover-one", "new fixture password")
        with Session(engine) as db:
            from lifeos.models import AccountLifecycle

            assert db.get(LoginSession, token_hash(session["token"])) is None
            assert db.get(AccountLifecycle, first).recovery_digest is None
            assert db.get(Account, second).enabled
            rows = db.execute(select(AccountLifecycle)).scalars().all()
            assert replacement not in json.dumps([r.recovery_digest for r in rows])
    finally:
        engine.dispose()


def test_recovery_routes_require_proof_csrf_and_return_no_store(setup_app, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("LIFEOS_ACCOUNT_MODE", "1")
    with TestClient(setup_app[2](), headers={"X-LifeOS-Key": "test-process-key"}) as web:
        # TrustedHost requires the internal loopback Host even in fixtures.
        web.headers["Host"] = "127.0.0.1"
        body = {"login": "route-recovery", "password": "fixture password"}
        assert web.post("/accounts/register", json=body).status_code == 201
        signed = web.post("/accounts/session", json=body).json()
        assert (
            web.post("/accounts/access/key", json={"password": "fixture password"}).status_code
            == 403
        )
        web.headers["X-CSRF-Token"] = signed["csrf"]
        response = web.post("/accounts/access/key", json={"password": "fixture password"})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        key = response.json()["recovery_key"]
        assert "recovery_key" not in web.get("/accounts/access").json()
        reset = {
            "login": body["login"],
            "recovery_key": key,
            "new_password": "replacement password",
        }
        assert web.post("/accounts/access/recover", json=reset).status_code == 204
        assert web.get("/accounts/access").status_code == 401
        assert web.post("/accounts/access/recover", json=reset).status_code == 401


def test_recovery_key_has_only_one_concurrent_success(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from lifeos.account_lifecycle import AccountLifecycleService

    engine = open_database(tmp_path)
    migrate(engine)
    auth = AccountService(engine, enabled=True)
    lifecycle = AccountLifecycleService(auth, tmp_path)
    owner = auth.register("concurrent-recovery", "fixture password")
    signed = auth.login("concurrent-recovery", "fixture password")
    key = lifecycle.generate_key(owner, signed["token"], "fixture password")["recovery_key"]
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda _: lifecycle.recover("concurrent-recovery", key, "replacement password"),
                    range(2),
                )
            )
        assert sorted(results) == [False, True]
    finally:
        engine.dispose()


def test_0044_migration_preserves_existing_account_password_and_session(tmp_path):
    from alembic import command
    from alembic.config import Config
    from lifeos.db import ROOT
    from lifeos.models import AccountLifecycle

    engine = open_database(tmp_path)
    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "services/api/alembic"))
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0043")
    auth = AccountService(engine, enabled=True)
    owner = auth.register("migration-lifecycle", "fixture password")
    signed = auth.login("migration-lifecycle", "fixture password")
    try:
        with Session(engine) as db:
            stored = db.get(Account, owner).password_digest
        migrate(engine)
        with Session(engine) as db:
            assert db.get(Account, owner).password_digest == stored
            assert db.get(LoginSession, token_hash(signed["token"])) is not None
            assert db.get(AccountLifecycle, owner) is None
    finally:
        engine.dispose()


def test_recovery_revokes_a_concurrent_old_password_login(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from threading import Event

    from lifeos import accounts
    from lifeos.account_lifecycle import AccountLifecycleService

    engine = open_database(tmp_path)
    migrate(engine)
    auth = AccountService(engine, enabled=True)
    service = AccountLifecycleService(auth, tmp_path)
    owner = auth.register("login-recovery-race", "fixture password")
    original = auth.login("login-recovery-race", "fixture password")
    key = service.generate_key(owner, original["token"], "fixture password")["recovery_key"]
    checked, release = Event(), Event()
    real_matches = accounts.matches

    def delayed_matches(password, stored):
        result = real_matches(password, stored)
        if password == "fixture password":
            checked.set()
            assert release.wait(10)
        return result

    monkeypatch.setattr(accounts, "matches", delayed_matches)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            login = pool.submit(auth.login, "login-recovery-race", "fixture password")
            assert checked.wait(5)
            reset = pool.submit(service.recover, "login-recovery-race", key, "replacement password")
            try:
                reset.result(timeout=1)
            except TimeoutError:
                pass  # A correctly fenced reset waits for the pending login transaction.
            finally:
                release.set()
            late = login.result(timeout=10)
            assert reset.result(timeout=10)
        with Session(engine) as db:
            assert db.get(LoginSession, token_hash(late["token"])) is None
    finally:
        release.set()
        engine.dispose()
