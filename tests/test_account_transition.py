import json

import pytest
from alembic import command
from alembic.config import Config
from lifeos.account_transition import apply_transition, preview_transition
from lifeos.db import ROOT, open_database
from lifeos.security import initialize_password
from sqlalchemy import text


def legacy_fixture(directory):
    directory.mkdir(parents=True, exist_ok=True)
    initialize_password(directory, "fixture personal password")
    engine = open_database(directory)
    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "services/api/alembic"))
    with engine.begin() as db:
        cfg.attributes["connection"] = db
        command.upgrade(cfg, "0028")
        db.execute(
            text("INSERT INTO settings VALUES(1,'Private name','he','dark','Asia/Jerusalem')")
        )
        db.execute(
            text(
                "INSERT INTO tasks(id,title,notes,priority,due,completed,created_at) VALUES('task','Private title','','medium',NULL,0,'2026-10-30T00:00:00Z')"
            )
        )
    engine.dispose()


def test_transition_preview_is_metadata_only_and_does_not_upgrade_source(tmp_path):
    legacy_fixture(tmp_path)
    database = tmp_path / "lifeos.sqlite3"
    before = database.read_bytes()
    auth_before = (tmp_path / "auth.json").read_bytes()
    proposal = preview_transition(tmp_path, "demo-owner")
    assert proposal["source_schema"] == "0028"
    assert proposal["target_login"] == "demo-owner"
    assert proposal["counts"]["tasks"] == 1
    assert "Private title" not in json.dumps(proposal)
    assert "Private name" not in json.dumps(proposal)
    assert "password" not in proposal
    assert database.read_bytes() == before
    assert (tmp_path / "auth.json").read_bytes() == auth_before
    assert len(proposal["source_digest"]) == 64


def test_transition_preview_requires_existing_source(tmp_path):
    with pytest.raises(FileNotFoundError):
        preview_transition(tmp_path / "missing", "demo-owner")
    assert not (tmp_path / "missing").exists()


def test_offline_transition_retains_password_records_and_existing_session(tmp_path):
    import sqlite3
    import time

    from lifeos.account_records import AccountRecords
    from lifeos.accounts import AccountService
    from lifeos.security import token_hash

    legacy_fixture(tmp_path)
    with sqlite3.connect(tmp_path / "lifeos.sqlite3") as db:
        db.execute(
            "INSERT INTO sessions VALUES(?,?,?)",
            (token_hash("fixture-session"), "fixture-csrf", int(time.time()) + 3600),
        )
    plan = preview_transition(tmp_path, "demo-owner")
    result = apply_transition(tmp_path, plan, approval_digest=plan["approval_digest"])
    assert result["account_id"] == plan["target_id"] and result["safety_backup_id"]
    assert json.loads((tmp_path / "account-mode.json").read_text())["enabled"]
    engine = open_database(tmp_path)
    try:
        assert AccountService(engine, enabled=True).login("demo-owner", "fixture personal password")
        assert (
            AccountRecords(engine).list(plan["target_id"], "tasks")[0]["title"] == "Private title"
        )
        with engine.connect() as db:
            assert (
                db.scalar(
                    text("SELECT account_id FROM sessions WHERE token_hash=:hash"),
                    {"hash": token_hash("fixture-session")},
                )
                == plan["target_id"]
            )
            assert db.scalar(text("SELECT count(*) FROM tasks WHERE account_id IS NULL")) == 0
        with pytest.raises(ValueError):
            apply_transition(tmp_path, plan, approval_digest=plan["approval_digest"])
    finally:
        engine.dispose()


def test_transition_rejects_unapproved_or_stale_plan_without_touching_source(tmp_path):
    import sqlite3

    legacy_fixture(tmp_path)
    plan = preview_transition(tmp_path, "demo-owner")
    before = (tmp_path / "lifeos.sqlite3").read_bytes()
    with pytest.raises(PermissionError):
        apply_transition(tmp_path, plan, approval_digest="wrong")
    assert (tmp_path / "lifeos.sqlite3").read_bytes() == before
    with sqlite3.connect(tmp_path / "lifeos.sqlite3") as db:
        db.execute("UPDATE tasks SET title='Changed after preview'")
    with pytest.raises(ValueError):
        apply_transition(tmp_path, plan, approval_digest=plan["approval_digest"])
    assert not (tmp_path / "account-mode.json").exists()


def test_transition_failure_keeps_original_and_explicit_rollback_restores_legacy(tmp_path):
    from lifeos.account_transition import rollback_transition

    legacy_fixture(tmp_path)
    plan = preview_transition(tmp_path, "demo-owner")

    def fail(staging):
        raise RuntimeError("Synthetic staged failure")

    with pytest.raises(RuntimeError):
        apply_transition(
            tmp_path, plan, approval_digest=plan["approval_digest"], before_install=fail
        )
    assert not (tmp_path / "account-mode.json").exists()
    fresh = preview_transition(tmp_path, "demo-owner")
    result = apply_transition(tmp_path, fresh, approval_digest=fresh["approval_digest"])
    restored = rollback_transition(
        tmp_path, result["safety_backup_id"], approval_digest=fresh["approval_digest"]
    )
    assert restored["restored_legacy_schema"] == "0028"
    assert not (tmp_path / "account-mode.json").exists()
    assert preview_transition(tmp_path, "demo-owner")["counts"]["tasks"] == 1


def test_transition_preserves_only_selected_google_cache_and_owned_mail_review(tmp_path):
    import sqlite3

    from lifeos.account_calendar import AccountCalendar
    from lifeos.account_mail import AccountMail
    from lifeos.account_providers import AccountProviders
    from lifeos.credential_vault import CredentialVault

    legacy_fixture(tmp_path)
    vault = CredentialVault(tmp_path)
    encrypted = vault.encrypt({"client_id": "synthetic-app", "refresh_token": "synthetic-token"})
    with sqlite3.connect(tmp_path / "lifeos.sqlite3") as db:
        for provider in ("google", "gmail"):
            db.execute(
                f"INSERT INTO {provider}_connection(id,credentials,state,last_success,next_sync,failures,lease_until) VALUES(1,?,'connected',1000,0,0,0)",
                (encrypted,),
            )
        for id, selected in (("selected", 1), ("hidden", 0)):
            db.execute(
                "INSERT INTO google_calendars VALUES(?,?,?,?,'old-token')",
                (id, id, "UTC", selected),
            )
            db.execute(
                "INSERT INTO google_records VALUES(?,?,'visible',?)",
                (id, id, json.dumps({"id": id})),
            )
        message = {
            "id": "mail",
            "subject": "Course fixture",
            "sender": "fixture@college.edu",
            "unread": True,
            "received_at": 1000,
        }
        db.execute("INSERT INTO gmail_messages VALUES('mail',?)", (json.dumps(message),))
        db.execute("INSERT INTO gmail_reviewed VALUES('mail')")
    plan = preview_transition(tmp_path, "demo-owner")
    apply_transition(tmp_path, plan, approval_digest=plan["approval_digest"])
    engine = open_database(tmp_path)
    try:
        calendar = AccountCalendar(engine, tmp_path)
        assert calendar.events(plan["target_id"]) == [{"id": "selected"}]
        assert AccountMail(engine).get(plan["target_id"])["queue"] == []
        lease = AccountProviders(engine, tmp_path).begin_sync(plan["target_id"], "google")
        assert lease["credentials"]["refresh_token"] == "synthetic-token"
        assert lease["credentials"]["selected_calendars"] == ["selected"]
    finally:
        engine.dispose()
