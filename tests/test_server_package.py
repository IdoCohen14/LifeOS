import importlib.util
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from lifeos.db import ROOT


def test_empty_server_persists_schema_and_data_without_replacing_credentials():
    import tempfile
    spec = importlib.util.spec_from_file_location("server_manage", ROOT / "scripts/server_manage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(dir=ROOT / ".runtime", prefix="server-package-") as base:
        data, config = Path(base) / "data", Path(base) / "config"
        module.initialize(data, config, "https://lifeos.example", fixture=True)
        original = (config / "runtime.env").read_bytes()
        key = (data / "provider.key").read_bytes()
        with closing(sqlite3.connect(data / "lifeos.sqlite3")) as db:
            assert db.execute("select version_num from alembic_version").fetchone()[0] == "0044"
            assert db.execute("select count(*) from accounts").fetchone()[0] == 0
            db.execute("create table package_persistence_fixture(value text)")
            db.execute("insert into package_persistence_fixture values ('retained')")
            db.commit()
        module.migrate_directory(data)
        with closing(sqlite3.connect(data / "lifeos.sqlite3")) as db:
            assert db.execute("select value from package_persistence_fixture").fetchone()[0] == "retained"
            assert db.execute("pragma foreign_key_check").fetchall() == []
        with pytest.raises(ValueError, match="empty data directory"):
            module.initialize(data, config, "https://other.example", fixture=True)
        assert (config / "runtime.env").read_bytes() == original
        assert (data / "provider.key").read_bytes() == key
        assert b"LIFEOS_API_KEY" not in (config / "edge.env").read_bytes()
