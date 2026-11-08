from datetime import datetime, timezone

PASSWORD = "separate scheduled fixture password"


def config(revision=0, **changes):
    return {
        "enabled": True,
        "clock": "08:00",
        "keep": 2,
        "revision": revision,
        "password": PASSWORD,
        "timezone": "Asia/Jerusalem",
        **changes,
    }


def service(setup_app, monkeypatch):
    from lifeos import scheduled_backups

    monkeypatch.setattr(
        scheduled_backups, "current_time", lambda: datetime(2026, 10, 27, 10, tzinfo=timezone.utc)
    )
    return scheduled_backups.ScheduledBackupService(
        setup_app[0].state.assistant.engine, setup_app[1]
    )


def test_backup_schedule_default_off_secret_redaction_cas_and_disable(
    client, setup_app, monkeypatch
):
    runner = service(setup_app, monkeypatch)
    initial = client.get("/recovery/schedule").json()
    assert not initial["enabled"] and not initial["configured"]
    assert runner.run_due() is None
    assert client.get("/recovery/backups").json() == []
    response = client.put("/recovery/schedule", json=config())
    assert response.status_code == 200
    saved = response.json()
    assert saved["enabled"] and saved["configured"] and saved["revision"] == 1
    assert PASSWORD not in response.text and "encrypted_password" not in saved
    assert client.put("/recovery/schedule", json=config()).status_code == 409
    off = client.put("/recovery/schedule", json=config(1, enabled=False, password=None)).json()
    assert not off["enabled"] and not off["configured"]
    assert client.put("/recovery/schedule", json=config(2, password=None)).status_code == 422


def test_due_backup_encrypted_retention_preserves_manual_and_backup_disables_schedule(
    client, setup_app, monkeypatch, tmp_path
):
    import sqlite3

    from lifeos.recovery import create_backup, unpack_backup

    runner = service(setup_app, monkeypatch)
    manual = create_backup(setup_app[1], PASSWORD)
    assert client.put("/recovery/schedule", json=config(keep=1)).status_code == 200
    first = runner.run_due()
    assert first and runner.run_due() is None
    folder = setup_app[1] / "backups"
    entries, manifest = unpack_backup(folder / (first["id"] + ".lifeosbackup"), PASSWORD)
    path = tmp_path / "inspected.sqlite3"
    path.write_bytes(entries["lifeos.sqlite3"])
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT enabled,encrypted_password FROM backup_schedule").fetchone() == (
            0,
            None,
        )
    from lifeos import scheduled_backups

    monkeypatch.setattr(
        scheduled_backups, "current_time", lambda: datetime(2026, 10, 28, 10, tzinfo=timezone.utc)
    )
    second = runner.run_due()
    assert second["id"] != first["id"]
    assert not (folder / (first["id"] + ".lifeosbackup")).exists()
    assert (folder / (manual["id"] + ".lifeosbackup")).exists()
    assert (folder / (second["id"] + ".lifeosbackup")).exists()


def test_backup_schedule_requires_csrf_and_valid_password(client, setup_app, monkeypatch):
    service(setup_app, monkeypatch)
    assert client.put("/recovery/schedule", json=config(password="short")).status_code == 422
    assert "short" not in client.put("/recovery/schedule", json=config(password="short")).text
    token = client.headers.pop("X-CSRF-Token")
    assert client.put("/recovery/schedule", json=config()).status_code == 403
    client.headers["X-CSRF-Token"] = token
    client.cookies.clear()
    assert client.get("/recovery/schedule").status_code == 401


def test_backup_lock_serializes_manual_worker_and_failure_backoff(client, setup_app, monkeypatch):
    import pytest
    from lifeos import scheduled_backups
    from lifeos.data_lock import backup_lock
    from lifeos.recovery import RecoveryError, create_backup

    runner = service(setup_app, monkeypatch)
    client.put("/recovery/schedule", json=config())
    with backup_lock(setup_app[1]):
        assert runner.run_due() is None
        with pytest.raises(RecoveryError, match="backup_busy"):
            create_backup(setup_app[1], PASSWORD)
    called = []

    def fail(*args):
        called.append(True)
        raise OSError("fixture path should never appear in status")

    monkeypatch.setattr(scheduled_backups, "_create_backup", fail)
    assert runner.run_due() is None
    assert runner.get()["last_error"] == "backup_failed"
    assert runner.run_due() is None and len(called) == 1
    monkeypatch.setattr(
        scheduled_backups,
        "current_time",
        lambda: datetime(2026, 10, 27, 10, 16, tzinfo=timezone.utc),
    )
    assert runner.run_due() is None and len(called) == 2


def test_backup_credential_encrypted_source_and_missing_files_safe(client, setup_app, monkeypatch):
    from lifeos.scheduled_backups import AutomaticBackupFile, BackupSchedule
    from sqlalchemy.orm import Session

    runner = service(setup_app, monkeypatch)
    client.put("/recovery/schedule", json=config(keep=1))
    with Session(runner.engine) as db:
        secret = db.get(BackupSchedule, 1).encrypted_password
        assert PASSWORD.encode() not in secret
        assert runner.vault.decrypt(secret)["password"] == PASSWORD
        db.add(AutomaticBackupFile(id="00000000-0000-0000-0000-000000000000", created_at=0))
        db.commit()
    result = runner.run_due()
    assert result
    with Session(runner.engine) as db:
        assert db.get(AutomaticBackupFile, "00000000-0000-0000-0000-000000000000") is None


def test_backup_schedule_stale_zone_and_dst_window_rejected(client, setup_app, monkeypatch):
    service(setup_app, monkeypatch)
    settings = client.get("/settings").json()
    client.put("/settings", json={**settings, "timezone": "UTC"})
    assert client.put("/recovery/schedule", json=config()).status_code == 409
    client.put("/settings", json=settings)
    assert client.put("/recovery/schedule", json=config(clock="01:30")).status_code == 422


def test_success_during_config_change_remains_visible_and_deduplicated(
    client, setup_app, monkeypatch
):
    from lifeos import scheduled_backups

    runner = service(setup_app, monkeypatch)
    client.put("/recovery/schedule", json=config())
    original = scheduled_backups._create_backup

    def changed(*args):
        response = client.put("/recovery/schedule", json=config(1, keep=3, password=None))
        assert response.status_code == 200
        return original(*args)

    monkeypatch.setattr(scheduled_backups, "_create_backup", changed)
    result = runner.run_due()
    assert result and runner.get()["last_success"] is not None
    monkeypatch.setattr(
        scheduled_backups,
        "current_time",
        lambda: datetime(2026, 10, 27, 10, 16, tzinfo=timezone.utc),
    )
    assert runner.run_due() is None


def test_published_file_metadata_failure_is_reported_without_deleting_file(
    client, setup_app, monkeypatch
):
    from sqlalchemy import event
    from sqlalchemy.exc import SQLAlchemyError

    runner = service(setup_app, monkeypatch)
    client.put("/recovery/schedule", json=config())
    attempts = []

    def fail_once(connection, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO automatic_backup_files") and not attempts:
            attempts.append(True)
            raise SQLAlchemyError("fixture registry failure")

    event.listen(runner.engine, "before_cursor_execute", fail_once)
    try:
        assert runner.run_due() is None
    finally:
        event.remove(runner.engine, "before_cursor_execute", fail_once)
    assert runner.get()["last_error"] == "backup_failed"
    assert len(client.get("/recovery/backups").json()) == 1


def test_retention_failure_stays_visible_and_retries_after_next_success(
    client, setup_app, monkeypatch
):
    from pathlib import Path

    from lifeos import scheduled_backups

    runner = service(setup_app, monkeypatch)
    client.put("/recovery/schedule", json=config(keep=1))
    first = runner.run_due()
    original = Path.unlink

    def cannot_delete(path, *args, **kwargs):
        if path.name == first["id"] + ".lifeosbackup":
            raise PermissionError("fixture open file")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", cannot_delete)
    monkeypatch.setattr(
        scheduled_backups, "current_time", lambda: datetime(2026, 10, 28, 10, tzinfo=timezone.utc)
    )
    assert runner.run_due()
    assert runner.get()["last_error"] == "backup_retention_pending"
    monkeypatch.setattr(Path, "unlink", original)
    monkeypatch.setattr(
        scheduled_backups, "current_time", lambda: datetime(2026, 10, 29, 10, tzinfo=timezone.utc)
    )
    assert runner.run_due()
    assert runner.get()["last_error"] is None
    assert not (setup_app[1] / "backups" / (first["id"] + ".lifeosbackup")).exists()


def test_backup_lock_excludes_separate_process_and_releases_after_owner(client, setup_app):
    import os
    import subprocess
    import sys
    from pathlib import Path

    from lifeos.data_lock import backup_lock

    code = """from pathlib import Path
import sys
from lifeos.data_lock import backup_lock
try:
    with backup_lock(Path(sys.argv[1])):
        print('acquired')
except RuntimeError:
    print('busy')
"""
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "services/api")}

    def probe():
        return subprocess.run(
            [sys.executable, "-c", code, str(setup_app[1])],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )

    with backup_lock(setup_app[1]):
        result = probe()
        assert result.returncode == 0 and result.stdout.strip() == "busy"
    result = probe()
    assert result.returncode == 0 and result.stdout.strip() == "acquired"


def test_actual_restore_keeps_unattended_backups_off(client, setup_app, monkeypatch, tmp_path):
    import sqlite3

    from lifeos.recovery import restore_backup

    runner = service(setup_app, monkeypatch)
    client.put("/recovery/schedule", json=config())
    saved = runner.run_due()
    target = tmp_path / "scheduled-restore-fixture"
    restore_backup(setup_app[1] / "backups" / (saved["id"] + ".lifeosbackup"), PASSWORD, target)
    with sqlite3.connect(target / "lifeos.sqlite3") as db:
        assert db.execute(
            "SELECT enabled,encrypted_password,last_success,last_attempt FROM backup_schedule"
        ).fetchone() == (0, None, None, None)


def test_scheduled_backup_worker_uses_recovery_guard_without_network(
    client, setup_app, monkeypatch
):
    import importlib.util
    from pathlib import Path

    import httpx
    import pytest
    from lifeos.data_lock import data_lock

    path = Path(__file__).resolve().parents[1] / "services/worker/worker.py"
    spec = importlib.util.spec_from_file_location("scheduled_backup_fixture_worker", path)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    called = []

    class Service:
        def __init__(self, engine, directory):
            pass

        def run_due(self):
            with pytest.raises(RuntimeError):
                with data_lock(setup_app[1]):
                    pytest.fail("Backup worker must hold runtime guard")
            called.append(True)

    monkeypatch.setattr(
        httpx, "Client", lambda *args, **kwargs: pytest.fail("No scheduled-backup network client")
    )
    monkeypatch.setattr(worker, "ScheduledBackupService", Service)
    worker.scheduled_backup()
    assert called == [True]
