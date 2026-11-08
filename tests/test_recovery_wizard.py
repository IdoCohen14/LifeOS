import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

PASSWORD = "wizard backup fixture password"
TOKEN = "fixture-capability-" * 3
ORIGIN = "http://127.0.0.1:8877"


@pytest.fixture
def wizard(client, setup_app, tmp_path):
    from lifeos.recovery import restore_backup
    from lifeos.recovery_ui import create_recovery_app
    from lifeos.security import initialize_password

    client.post("/tasks", json={"title": "Saved fixture"})
    saved = client.post("/recovery/backups", json={"password": PASSWORD}).json()
    source = setup_app[1] / "backups" / (saved["id"] + ".lifeosbackup")
    target = tmp_path / "wizard-target"
    restore_backup(source, PASSWORD, target)
    (target / "auth.json").unlink()
    initialize_password(target, "current fixture login password")
    (target / "backups").mkdir(exist_ok=True)
    (target / "backups" / source.name).write_bytes(source.read_bytes())
    with sqlite3.connect(target / "lifeos.sqlite3") as db:
        db.execute("update tasks set title='Current fixture'")
    app = create_recovery_app(target, TOKEN, port=8877, test_mode=True)
    with TestClient(
        app, base_url=ORIGIN, headers={"X-Recovery-Token": TOKEN, "Origin": ORIGIN}
    ) as ui:
        yield ui, target, saved["id"], app


def inspect(ui, backup_id):
    response = ui.post("/api/inspect", json={"backup_id": backup_id, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def title(target):
    with sqlite3.connect(target / "lifeos.sqlite3") as db:
        return db.execute("select title from tasks").fetchone()[0]


def test_wizard_inspect_then_explicit_restore_and_idempotent_retry(wizard):
    ui, target, backup_id, _ = wizard
    from lifeos.security import verify_password

    assert verify_password(target, "current fixture login password")
    state = ui.get("/api/state").json()
    assert state["directory"] == str(target.resolve()) and state["test_mode"] is True
    assert [row["id"] for row in state["backups"]] == [backup_id]
    plan = inspect(ui, backup_id)
    assert plan["counts"]["tasks"] == 1 and title(target) == "Current fixture"
    assert PASSWORD not in str(plan) and TOKEN not in str(plan)
    assert (
        ui.post(
            "/api/restore", json={"id": plan["id"], "password": PASSWORD, "confirm": False}
        ).status_code
        == 422
    )
    assert (
        ui.post(
            "/api/restore", json={"id": plan["id"], "password": PASSWORD, "confirm": "true"}
        ).status_code
        == 422
    )
    response = ui.post(
        "/api/restore", json={"id": plan["id"], "password": PASSWORD, "confirm": True}
    )
    assert response.status_code == 200, response.text
    assert title(target) == "Saved fixture" and response.json()["safety_backup_id"]
    assert verify_password(target, "correct horse battery staple")
    assert not verify_password(target, "current fixture login password")
    assert (
        ui.post(
            "/api/restore", json={"id": plan["id"], "password": PASSWORD, "confirm": True}
        ).json()
        == response.json()
    )
    assert (
        ui.post("/api/inspect", json={"backup_id": backup_id, "password": PASSWORD}).status_code
        == 409
    )
    with sqlite3.connect(target / "lifeos.sqlite3") as db:
        assert db.execute("select count(*) from sessions").fetchone()[0] == 0


def test_wizard_auth_origin_host_body_redaction_and_safe_listing(wizard):
    ui, target, backup_id, _ = wizard
    assert ui.get("/api/state", headers={"X-Recovery-Token": "wrong"}).status_code == 401
    assert ui.get("/api/state", headers={"Host": "evil.invalid"}).status_code == 403
    assert (
        ui.post(
            "/api/inspect",
            headers={"Origin": "https://evil.invalid"},
            json={"backup_id": backup_id, "password": PASSWORD},
        ).status_code
        == 403
    )
    response = ui.post(
        "/api/inspect", json={"backup_id": backup_id, "password": 123, "secret": "must-not-echo"}
    )
    assert response.status_code == 422 and "must-not-echo" not in response.text
    assert ui.post("/api/inspect", content=b"x" * 8193).status_code == 413
    assert (
        ui.post("/api/inspect", json={"backup_id": "../auth", "password": PASSWORD}).status_code
        == 404
    )
    (target / "backups" / "not-a-uuid.lifeosbackup").write_bytes(b"fixture")
    assert [row["id"] for row in ui.get("/api/state").json()["backups"]] == [backup_id]
    assert ui.get("/").headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in ui.get("/").headers["content-security-policy"]


def test_wizard_review_expiry_source_changes_and_live_writer_lock(wizard, monkeypatch):
    from lifeos import recovery_ui
    from lifeos.data_lock import runtime_lock

    ui, target, backup_id, _ = wizard
    now = time.monotonic()
    clock = [now]
    monkeypatch.setattr(recovery_ui.time, "monotonic", lambda: clock[0])
    plan = inspect(ui, backup_id)
    clock[0] += 601
    assert (
        ui.post(
            "/api/restore", json={"id": plan["id"], "password": PASSWORD, "confirm": True}
        ).status_code
        == 409
    )
    clock[0] = now
    plan = inspect(ui, backup_id)
    with runtime_lock(target):
        response = ui.post(
            "/api/restore", json={"id": plan["id"], "password": PASSWORD, "confirm": True}
        )
    assert response.status_code == 409 and title(target) == "Current fixture"
    path = target / "backups" / (backup_id + ".lifeosbackup")
    original = path.read_bytes()
    path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
    assert (
        ui.post(
            "/api/restore", json={"id": plan["id"], "password": PASSWORD, "confirm": True}
        ).status_code
        == 409
    )
    assert title(target) == "Current fixture"
    path.write_bytes(original)
    clock[0] = now + 1801
    assert ui.get("/api/state").status_code == 401


def test_wizard_wrong_password_rate_limit_and_latest_preview_only(wizard):
    ui, target, backup_id, _ = wizard
    one = inspect(ui, backup_id)
    two = inspect(ui, backup_id)
    assert one["id"] != two["id"]
    assert (
        ui.post(
            "/api/restore", json={"id": one["id"], "password": PASSWORD, "confirm": True}
        ).status_code
        == 409
    )
    for _ in range(5):
        response = ui.post(
            "/api/inspect", json={"backup_id": backup_id, "password": "wrong fixture password"}
        )
        assert response.status_code == 422 and "wrong fixture password" not in response.text
    assert (
        ui.post("/api/inspect", json={"backup_id": backup_id, "password": PASSWORD}).status_code
        == 429
    )
    assert title(target) == "Current fixture"


def test_wizard_expiry_after_replacement_copy_rolls_back_before_commit(wizard, monkeypatch):
    from pathlib import Path

    from lifeos import recovery, recovery_ui

    ui, target, backup_id, _ = wizard
    now = time.monotonic()
    clock = [now]
    monkeypatch.setattr(recovery_ui.time, "monotonic", lambda: clock[0])
    plan = inspect(ui, backup_id)
    copy = recovery.copy_database
    replaced = []

    def delayed(source, destination):
        copy(source, destination)
        if Path(destination) == target / "lifeos.sqlite3":
            replaced.append(True)
            clock[0] = now + 601

    monkeypatch.setattr(recovery, "copy_database", delayed)
    response = ui.post(
        "/api/restore", json={"id": plan["id"], "password": PASSWORD, "confirm": True}
    )
    assert response.status_code == 409, response.text
    assert replaced and title(target) == "Current fixture"
    assert not (target / ".restore-in-progress").exists()


@pytest.mark.parametrize(
    "args",
    [
        ["--test-mode", "--data-dir", ".", "--token-file", ".runtime/should-not-exist"],
        ["--no-browser"],
        ["--token-file", ".runtime/should-not-exist"],
    ],
)
def test_wizard_launcher_rejects_unsafe_fixture_or_capability_modes(args):
    import subprocess
    import sys

    from lifeos.db import ROOT

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/recovery_ui.py"), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert not (ROOT / ".runtime/should-not-exist").exists()


def test_wizard_busy_rejects_overlap_without_second_decryption(wizard, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from lifeos import recovery_ui

    ui, target, backup_id, _ = wizard
    entered = threading.Event()
    release = threading.Event()
    original = recovery_ui.inspect_backup

    def held(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(recovery_ui, "inspect_backup", held)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            ui.post, "/api/inspect", json={"backup_id": backup_id, "password": PASSWORD}
        )
        try:
            assert entered.wait(10)
            assert (
                ui.post(
                    "/api/inspect", json={"backup_id": backup_id, "password": PASSWORD}
                ).status_code
                == 409
            )
        finally:
            release.set()
        assert pending.result(timeout=10).status_code == 200
    assert title(target) == "Current fixture"


def test_wizard_directory_discovery_refuses_ambiguous_profiles(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path

    from lifeos import db
    from lifeos.db import ROOT

    spec = importlib.util.spec_from_file_location(
        "fixture_recovery_launcher", ROOT / "scripts/recovery_ui.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    default = tmp_path / "default"
    packaged = tmp_path / "AppData/Local/Packages/OpenAI.Codex_fixture/LocalCache/Local/LifeOS"
    default.mkdir()
    packaged.mkdir(parents=True)
    monkeypatch.setattr(db, "data_directory", lambda: default)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for name in ("auth.json", "lifeos.sqlite3"):
        (packaged / name).write_bytes(b"fixture presence only")
    assert module.resolve_directory() == packaged.resolve()
    for name in ("auth.json", "lifeos.sqlite3"):
        (default / name).write_bytes(b"fixture presence only")
    if module.os.name == "nt":
        with pytest.raises(SystemExit, match="Multiple"):
            module.resolve_directory()
    assert module.resolve_directory(default) == default.resolve()


def test_external_file_upload_is_reviewed_then_restored_to_fixture_only(wizard):
    ui, target, backup_id, _ = wizard
    source = target / "backups" / (backup_id + ".lifeosbackup")
    encrypted = source.read_bytes()
    response = ui.post(
        "/api/upload",
        content=encrypted,
        headers={
            "Content-Type": "application/octet-stream",
            "X-Backup-Name": "selected-fixture.lifeosbackup",
        },
    )
    assert response.status_code == 200, response.text
    uploaded = response.json()
    assert uploaded["name"] == "selected-fixture.lifeosbackup"
    preview = inspect(ui, uploaded["id"])
    assert title(target) == "Current fixture"
    assert preview["source_name"] == "selected-fixture.lifeosbackup"
    assert (
        ui.post(
            "/api/restore", json={"id": preview["id"], "password": PASSWORD, "confirm": False}
        ).status_code
        == 422
    )
    response = ui.post(
        "/api/restore", json={"id": preview["id"], "password": PASSWORD, "confirm": True}
    )
    assert response.status_code == 200, response.text
    assert title(target) == "Saved fixture"
    assert source.read_bytes() == encrypted


def test_uploaded_backup_limit_preserves_current_fixture(wizard, monkeypatch):
    from lifeos import recovery_ui

    ui, target, _, _ = wizard
    monkeypatch.setattr(recovery_ui, "MAX_PACKAGE", 16)
    response = ui.post(
        "/api/upload",
        content=b"x" * 145,
        headers={
            "Content-Type": "application/octet-stream",
            "X-Backup-Name": "fixture.lifeosbackup",
        },
    )
    assert response.status_code == 413
    assert title(target) == "Current fixture"
