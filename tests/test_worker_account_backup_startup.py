import os
import subprocess
import sys
from pathlib import Path

from lifeos.account_backup_schedule import AccountBackupSchedule
from lifeos.accounts import AccountService


def test_fresh_worker_process_can_create_scheduled_account_archive(client, setup_app):
    engine, directory = setup_app[0].state.assistant.engine, setup_app[1]
    owner = AccountService(engine, enabled=True).register("worker-backup-fixture", "fixture password")
    schedule = AccountBackupSchedule(engine, directory)
    schedule.configure(owner, {
        "enabled": True, "clock": "00:00", "keep": 7, "revision": 0,
        "password": "fixture archive password", "timezone": "Asia/Jerusalem",
    })
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "LIFEOS_DATA_DIR": str(directory), "LIFEOS_ACCOUNT_MODE": "1"}
    result = subprocess.run(
        [sys.executable, "-c", "import runpy; worker=runpy.run_path('services/worker/worker.py', run_name='fixture_worker'); worker['scheduled_backup']()"],
        cwd=root, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    status = schedule.get(owner)
    assert status["last_success"] is not None, status["last_error"]
    assert status["last_error"] is None
    backups = schedule.list(owner)
    assert len(backups) == 1
    assert schedule.read(owner, backups[0]["id"], "fixture archive password")["account_id"] == owner
