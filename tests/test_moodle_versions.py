import httpx
import pytest
from lifeos.account_academic import AccountAcademic
from lifeos.account_moodle import AccountMoodle
from lifeos.account_records import AccountRecords
from lifeos.accounts import AccountService
from lifeos.braude_academic import BraudeAcademic
from lifeos.google_calendar import GoogleProblem
from lifeos.moodle import parse_feed
from test_braude_academic import roster_file


def event(day="05", modified="20261101T100000Z", title="Lab is due"):
    stamp = f"LAST-MODIFIED:{modified}\r\n" if modified else ""
    return (f"BEGIN:VEVENT\r\nUID:stable-fixture\r\nSUMMARY:{title}\r\n"
            f"DTSTART:202611{day}T150000Z\r\nCATEGORIES:Course (2027_1_6_12345)\r\n"
            + stamp + "END:VEVENT\r\n")


def feed(*events):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + "".join(events) + "END:VCALENDAR\r\n").encode()


@pytest.mark.parametrize("reverse", [False, True])
def test_same_uid_uses_proven_latest_source_version_independent_of_order(reverse):
    events = [event(), event("12", "20261102T100000Z", "Lab is due (extension)")]
    rows = parse_feed(feed(*(events[::-1] if reverse else events)), "moodle27.braude.ac.il")
    assert len(rows) == 1 and rows[0]["start"] == "2026-11-12T15:00:00Z"
    assert rows[0]["source_modified_at"] == "2026-11-02T10:00:00Z"
    assert len(parse_feed(feed(events[0], events[0]), "moodle27.braude.ac.il")) == 1


@pytest.mark.parametrize("modified", [None, "20261101T100000Z"])
def test_conflicting_duplicate_without_proven_order_is_not_last_row_wins(modified):
    with pytest.raises(GoogleProblem) as error:
        parse_feed(feed(event(modified=modified), event("12", modified)), "moodle27.braude.ac.il")
    assert error.value.code == "conflicting_calendar_event"


def test_extension_sync_retains_completion_and_rejects_source_rollback(client, setup_app, tmp_path):
    engine, directory = setup_app[0].state.assistant.engine, setup_app[1]
    owner = AccountService(engine, enabled=True).register("version-owner", "fixture password")
    BraudeAcademic(engine).import_roster(owner, roster_file(tmp_path), year=2027, semester=1,
                                       start_date="2026-10-02", end_date="2027-01-30")
    store = AccountMoodle(engine, directory)
    store.configure(owner, "moodle", {"url": "https://moodle27.braude.ac.il/calendar/export_execute.php?authtoken=fixture"})
    content = [feed(event())]
    def factory(**kwargs):
        return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=content[0])), **kwargs)
    records = AccountRecords(engine)
    store.sync(owner, client_factory=factory)
    original = records.list(owner, "tasks")[0]
    records.save(owner, "tasks", {**original, "completed": True}, original["id"])
    content[0] = feed(event("12", "20261102T100000Z", "Lab is due (extension)"))
    store.sync(owner, client_factory=factory)
    extended = records.list(owner, "tasks")[0]
    assert extended["id"] == original["id"] and extended["completed"]
    assert extended["due"] == "2026-11-12T15:00:00Z"
    content[0] = feed(event())
    store.sync(owner, client_factory=factory)
    assert records.list(owner, "tasks")[0] == extended
    assert store.records(owner, "moodle")[0]["start"] == extended["due"]
    assert len(AccountAcademic(engine).list_children(owner, "items")) == 1
    # Failed conflicting snapshot preserves both task and the previous cache.
    before = store.records(owner, "moodle")
    content[0] = feed(event("13", None), event("14", None))
    with pytest.raises(GoogleProblem):
        store.sync(owner, client_factory=factory)
    assert store.records(owner, "moodle") == before
    assert records.list(owner, "tasks")[0] == extended
