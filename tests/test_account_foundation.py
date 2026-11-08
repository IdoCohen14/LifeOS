from alembic import command
from alembic.config import Config
from lifeos.db import ROOT, open_database
from sqlalchemy import text


def test_account_upgrade_preserves_legacy_session_and_enforces_owner_reference(tmp_path):
    engine = open_database(tmp_path)
    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "services/api/alembic"))
    with engine.begin() as db:
        cfg.attributes["connection"] = db
        command.upgrade(cfg, "0028")
        db.execute(
            text("INSERT INTO sessions(token_hash,csrf,expires) VALUES('legacy','fixture',12345)")
        )
        db.execute(
            text(
                "CREATE TABLE migration_fixture_session_links(id TEXT PRIMARY KEY,session_hash TEXT REFERENCES sessions(token_hash) ON DELETE CASCADE)"
            )
        )
        db.execute(text("INSERT INTO migration_fixture_session_links VALUES('linked','legacy')"))
        command.upgrade(cfg, "0029")
        assert db.scalar(text("SELECT count(*) FROM migration_fixture_session_links")) == 1
        assert db.execute(
            text("SELECT token_hash,csrf,expires,account_id FROM sessions")
        ).one() == ("legacy", "fixture", 12345, None)
        assert db.scalar(text("SELECT count(*) FROM accounts")) == 0
        db.execute(
            text(
                "INSERT INTO accounts VALUES('account-fixture','fixture@example.test','synthetic-digest','2026-10-29T00:00:00Z',1)"
            )
        )
        db.execute(text("INSERT INTO sessions VALUES('owned','fixture',12345,'account-fixture')"))
        db.execute(text("DELETE FROM accounts WHERE id='account-fixture'"))
        assert db.scalar(text("SELECT count(*) FROM sessions WHERE token_hash='owned'")) == 0
        assert db.scalar(text("SELECT count(*) FROM sessions WHERE token_hash='legacy'")) == 1
    engine.dispose()


def test_manual_owner_migration_preserves_referencing_records_and_can_downgrade(tmp_path):
    engine = open_database(tmp_path)
    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "services/api/alembic"))
    with engine.begin() as db:
        cfg.attributes["connection"] = db
        command.upgrade(cfg, "0029")
        db.execute(
            text(
                "INSERT INTO tasks(id,title,notes,priority,due,completed,created_at) VALUES('legacy','Fixture','original','medium',NULL,0,'2026-10-29T00:00:00Z')"
            )
        )
        db.execute(
            text(
                "CREATE TABLE migration_fixture_links(id TEXT PRIMARY KEY,task_id TEXT REFERENCES tasks(id) ON DELETE CASCADE)"
            )
        )
        db.execute(text("INSERT INTO migration_fixture_links VALUES('link','legacy')"))
        command.upgrade(cfg, "0030")
        assert db.scalar(text("SELECT account_id FROM tasks WHERE id='legacy'")) is None
        assert db.scalar(text("SELECT count(*) FROM migration_fixture_links")) == 1
        assert db.scalar(text("SELECT notes FROM tasks WHERE id='legacy'")) == "original"
        command.downgrade(cfg, "0029")
        assert db.scalar(text("SELECT count(*) FROM migration_fixture_links")) == 1
        assert db.scalar(text("SELECT notes FROM tasks WHERE id='legacy'")) == "original"
    engine.dispose()
