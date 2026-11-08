import json
from uuid import uuid4

import pytest


def test_saved_account_build_defaults_and_rejects_paths(tmp_path):
    from lifeos.account_transition import saved_account_build

    marker = {"version": 1, "enabled": True, "account_id": str(uuid4())}
    path = tmp_path / "account-mode.json"
    path.write_text(json.dumps(marker))
    assert saved_account_build(tmp_path) == ".next-account-release"
    marker["web_build_dir"] = ".next-lifecycle-release"
    path.write_text(json.dumps(marker))
    assert saved_account_build(tmp_path) == ".next-lifecycle-release"
    marker["web_build_dir"] = "../../private"
    path.write_text(json.dumps(marker))
    with pytest.raises(ValueError):
        saved_account_build(tmp_path)


def test_offline_release_stages_migration_and_preserves_account_rows(tmp_path):
    from alembic import command
    from alembic.config import Config
    from lifeos import academic_models  # noqa: F401
    from lifeos.accounts import AccountService
    from lifeos.db import ROOT, open_database
    from lifeos.local_release import activate_account_release
    from lifeos.security import initialize_password

    initialize_password(tmp_path, "fixture installation password")
    engine = open_database(tmp_path)
    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "services/api/alembic"))
    with engine.begin() as db:
        cfg.attributes["connection"] = db
        command.upgrade(cfg, "0043")
    auth = AccountService(engine, enabled=True)
    owner = auth.register("fixture-release", "fixture password")
    signed = auth.login("fixture-release", "fixture password")
    engine.dispose()
    (tmp_path / "account-mode.json").write_text(
        json.dumps({"version": 1, "enabled": True, "account_id": owner})
    )
    result = activate_account_release(tmp_path, owner, ".next-fixture-release")
    assert result["schema"] == "0044" and result["existing_rows_preserved"]
    assert (tmp_path / "backups" / (result["safety_backup_id"] + ".lifeosbackup")).is_file()
    assert not (tmp_path / ".restore-in-progress").exists()
    from lifeos.account_transition import saved_account_build

    assert saved_account_build(tmp_path) == ".next-fixture-release"
    assert signed["token"] not in (tmp_path / "account-mode.json").read_text()
