import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("test_mode", [False, True])
def test_actual_launched_child_tempfile_belongs_to_its_data_directory(
    tmp_path, monkeypatch, test_mode
):
    from types import SimpleNamespace

    from lifeos import db
    from lifeos.db import ROOT

    monkeypatch.setenv("LIFEOS_TEST_MODE", "")
    monkeypatch.setattr(sys, "path", list(sys.path))
    original_python = sys.executable
    spec = importlib.util.spec_from_file_location("fixture_temp_launcher", ROOT / "scripts/run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fake_root = tmp_path / "repository"
    data = fake_root / ".runtime/profile" if test_mode else tmp_path / "private-data"
    data.mkdir(parents=True)
    (data / "auth.json").write_text("fixture not used for authentication", encoding="utf-8")
    fake_python = fake_root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    fake_python.parent.mkdir(parents=True)
    fake_python.touch()
    build = fake_root / "apps/web/.next"
    build.mkdir(parents=True)
    (build / "BUILD_ID").write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", fake_root)
    monkeypatch.setattr(sys, "executable", str(fake_python))
    monkeypatch.setattr(
        sys,
        "argv",
        [str(ROOT / "scripts/run.py"), "--no-browser", *(["--test-mode"] if test_mode else [])],
    )
    monkeypatch.setattr(db, "data_directory", lambda: data)

    class Engine:
        def dispose(self):
            pass

    monkeypatch.setattr(db, "open_database", lambda _: Engine())
    monkeypatch.setattr(db, "migrate", lambda _: None)
    # This launcher test stubs the database; account-mode detection has its own tests.
    from lifeos import account_operations

    monkeypatch.setattr(account_operations, "account_runtime", lambda _: False)

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def bind(self, address):
            assert address[0] == "127.0.0.1"

    monkeypatch.setattr(module.socket, "socket", Socket)
    monkeypatch.setattr(module.shutil, "which", lambda _: "fixture-npm")
    cleanups = []
    monkeypatch.setattr(module.atexit, "register", cleanups.append)
    actual_run = subprocess.run
    captured = {}

    class Child:
        def poll(self):
            return 0

        def wait(self, timeout):
            return 0

    def supervisor(_command, *, cwd, env, creationflags):
        captured.update({key: env[key] for key in ("TEMP", "TMP", "TMPDIR")})
        # Real stdlib tempfile behavior in a fresh child, not an assertion about a helper.
        result = actual_run(
            [
                original_python,
                "-c",
                "import tempfile,json; f=tempfile.NamedTemporaryFile(delete=False); f.write(b'fixture only'); f.close(); print(json.dumps(f.name))",
            ],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        captured["file"] = Path(json.loads(result.stdout))
        return Child()

    monkeypatch.setattr(
        module,
        "subprocess",
        SimpleNamespace(
            Popen=supervisor,
            run=actual_run,
            call=subprocess.call,
            CREATE_NO_WINDOW=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ),
    )
    try:
        with pytest.raises(SystemExit, match="A service exited"):
            module.main()
    finally:
        for cleanup in cleanups:
            cleanup()
    assert captured["file"].parent == data / "tmp"
    assert captured["file"].read_bytes() == b"fixture only"
    assert all(Path(captured[key]) == data / "tmp" for key in ("TEMP", "TMP", "TMPDIR"))
    assert not (fake_root / ".runtime/tmp").exists()
