import pytest
from lifeos.accounts import AccountService
from lifeos.models import Account, LoginSession
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_internal_accounts_normalize_logins_and_keep_session_ownership(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    service = AccountService(engine, enabled=True)
    first = service.register(" First@Example.Test ", "fixture password one")
    second = service.register("second@example.test", "fixture password two")
    with pytest.raises(ValueError):
        service.register("FIRST@example.test", "different password")
    assert service.login("unknown@example.test", "fixture password one") is None
    assert service.login("first@example.test", "wrong password") is None
    a = service.login("FIRST@example.test", "fixture password one")
    b = service.login("second@example.test", "fixture password two")
    assert a["account_id"] == first and b["account_id"] == second and a["token"] != b["token"]
    with Session(engine) as db:
        assert all(
            row.token_hash not in (a["token"], b["token"])
            for row in db.scalars(select(LoginSession))
        )
        assert "fixture password" not in db.get(Account, first).password_digest
    client.cookies.set("lifeos_session", a["token"], domain="127.0.0.1", path="/")
    assert client.get("/tasks").status_code == 403


def test_account_authentication_is_inactive_by_default_and_bounded(client, setup_app):
    service = AccountService(setup_app[0].state.assistant.engine)
    with pytest.raises(RuntimeError):
        service.register("fixture", "fixture password")
    service.enabled = True
    for _ in range(10):
        assert service.login("missing", "fixture password") is None
    with pytest.raises(RuntimeError):
        service.login("missing", "fixture password")


def test_password_change_revokes_only_owner_sessions_and_logout_is_token_scoped(client, setup_app):
    from lifeos.security import token_hash

    engine = setup_app[0].state.assistant.engine
    service = AccountService(engine, enabled=True)
    a = service.register("password-a", "fixture password a")
    b = service.register("password-b", "fixture password b")
    sa = service.login("password-a", "fixture password a")
    sb = service.login("password-b", "fixture password b")
    assert service.change_password(a, "wrong password", "replacement password") is False
    assert service.change_password(a, "fixture password a", "replacement password") is True
    with Session(engine) as db:
        assert db.get(LoginSession, token_hash(sa["token"])) is None
        assert db.get(LoginSession, token_hash(sb["token"])).account_id == b
    assert service.login("password-a", "fixture password a") is None
    fresh = service.login("password-a", "replacement password")
    assert fresh["account_id"] == a
    service.logout(fresh["token"])
    with Session(engine) as db:
        assert db.get(LoginSession, token_hash(fresh["token"])) is None
        assert db.get(LoginSession, token_hash(sb["token"])) is not None
