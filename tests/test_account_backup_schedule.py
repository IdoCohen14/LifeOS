from datetime import datetime, timezone

from lifeos.account_archive import AccountArchive
from lifeos.account_backup_schedule import AccountBackupSchedule
from lifeos.accounts import AccountService


def test_owned_backup_schedule_is_opt_in_daily_and_does_not_prune_manual_files(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    a = auth.register("scheduled-a", "fixture password a")
    b = auth.register("scheduled-b", "fixture password b")
    schedule = AccountBackupSchedule(engine, setup_app[1])
    now = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
    assert schedule.run_due(a, now=now) is None
    for owner in (a, b):
        schedule.configure(
            owner,
            {
                "enabled": True,
                "clock": "00:30",
                "keep": 1,
                "revision": 0,
                "password": "fixture backup password",
                "timezone": "Asia/Jerusalem",
            },
            now=now,
        )
    archive = AccountArchive(engine, setup_app[1])
    manual = archive.create(a, "fixture backup password")
    first = schedule.run_due(a, now=now)
    assert first and schedule.run_due(a, now=now) is None
    assert archive.list(b) == []
    second = schedule.run_due(a, now=datetime(2026, 11, 2, 12, tzinfo=timezone.utc))
    assert {row["id"] for row in archive.list(a)} == {manual["id"], second["id"]}
    assert first["id"] not in {row["id"] for row in archive.list(a)}
    assert schedule.get(a)["last_success"] and schedule.get(b)["last_success"] is None
    assert "password" not in str(schedule.get(a))
    schedule.configure(
        a,
        {
            "enabled": False,
            "clock": "00:30",
            "keep": 1,
            "revision": 1,
            "timezone": "Asia/Jerusalem",
        },
        now=now,
    )
    assert not schedule.get(a)["configured"]
    assert schedule.run_due(a, now=datetime(2026, 11, 3, 12, tzinfo=timezone.utc)) is None
