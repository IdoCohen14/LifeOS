"""Owned source memory survives a logical archive and a fresh authorized feed sync."""

import httpx
import pytest
from lifeos.academic_models import AcademicItem
from lifeos.account_academic import AccountAcademic
from lifeos.account_archive import AccountArchive
from lifeos.account_moodle import AccountMoodle
from lifeos.account_records import AccountRecords
from lifeos.account_restore import AccountRestore
from lifeos.accounts import AccountService
from lifeos.braude_academic import BraudeAcademic
from lifeos.models import AccountPreference, AccountProvider
from sqlalchemy.orm import Session
from test_braude_academic import roster_file


@pytest.mark.parametrize("local_state", ["completed", "edited", "deleted"])
def test_moodle_reconnect_after_restore_keeps_local_decisions(
    client, setup_app, tmp_path, local_state
):
    engine, directory = setup_app[0].state.assistant.engine, setup_app[1]
    accounts = AccountService(engine, enabled=True)
    owner = accounts.register("source-restore", "fixture password")
    other = accounts.register("other-source-restore", "fixture password")
    token = accounts.login("source-restore", "fixture password")["token"]
    records = AccountRecords(engine)
    untouched = records.save(other, "tasks", {"title": "Other owner fixture"})
    BraudeAcademic(engine).import_roster(
        owner, roster_file(tmp_path), year=2027, semester=1,
        start_date="2026-10-02", end_date="2027-01-30",
    )
    moodle = AccountMoodle(engine, directory)
    config = {"url": "https://moodle27.braude.ac.il/calendar/export_execute.php?authtoken=fixture"}
    moodle.configure(owner, "moodle", config)
    source = {"day": "20261105"}

    def factory(**kwargs):
        def feed(_request):
            raw = (
                "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\n"
                "UID:restore-assignment@moodle27.braude.ac.il\r\n"
                f"DTSTART:{source['day']}T200000Z\r\n"
                "SUMMARY:Lab restore is due\r\n"
                "CATEGORIES:Course (2027_1_6_12345)\r\n"
                "END:VEVENT\r\nEND:VCALENDAR\r\n"
            )
            return httpx.Response(200, content=raw.encode())
        return httpx.Client(transport=httpx.MockTransport(feed), **kwargs)

    moodle.sync(owner, client_factory=factory)
    task = records.list(owner, "tasks")[0]
    with Session(engine) as db:
        item = db.get(AcademicItem, task["academic_id"])
        if local_state == "completed":
            item.task.completed = True
        elif local_state == "edited":
            item.due = item.task.due = "2026-11-09"
        else:
            linked = item.task
            db.delete(item)
            db.flush()
            db.delete(linked)
        db.commit()

    archive = AccountArchive(engine, directory)
    saved = archive.create(owner, "fixture archive password")
    records.save(owner, "tasks", {"title": "After snapshot fixture"})
    restore = AccountRestore(engine, directory)
    preview = restore.preview(owner, token, saved["id"], "fixture archive password")
    result = restore.confirm(owner, token, preview["id"], "fixture archive password")
    assert result["reconnect_required"] and result["relogin_required"]
    with Session(engine) as db:
        provider = db.get(AccountProvider, (owner, "moodle"))
        assert not provider.authorized and provider.credentials is None
        assert db.get(AccountPreference, (owner, "moodle_academic")) is not None
    assert moodle.records(owner, "moodle") == []

    # Reconnect is explicit; no secret was restored from the archive.
    moodle.configure(owner, "moodle", config)
    source["day"] = "20261106"
    moodle.sync(owner, client_factory=factory)
    moodle.sync(owner, client_factory=factory)
    restored = records.list(owner, "tasks")
    items = AccountAcademic(engine).list_children(owner, "items")
    if local_state == "deleted":
        assert restored == [] and items == []
        assert len(moodle.records(owner, "moodle", calendar_only=True)) == 1
    else:
        assert len(restored) == len(items) == 1
        assert restored[0]["id"] == task["id"]
        assert restored[0]["academic_id"] == task["academic_id"]
        assert restored[0]["completed"] == (local_state == "completed")
        assert restored[0]["due"] == (
            "2026-11-09" if local_state == "edited" else "2026-11-06T20:00:00Z"
        )
    assert records.list(other, "tasks")[0]["id"] == untouched["id"]
