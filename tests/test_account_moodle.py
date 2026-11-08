import httpx
import pytest
from lifeos.account_moodle import AccountMoodle
from lifeos.accounts import AccountService
from lifeos.google_calendar import GoogleProblem


def test_account_moodle_uses_owned_feed_and_preserves_cache_on_redirect(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    accounts = AccountService(engine, enabled=True)
    a = accounts.register("moodle-a", "fixture password a")
    b = accounts.register("moodle-b", "fixture password b")
    store = AccountMoodle(engine, setup_app[1])
    redirect = [False]

    def handler(request):
        if redirect[0]:
            return httpx.Response(302, headers={"Location": "https://example.invalid/forbidden"})
        name = request.url.params["authtoken"]
        content = f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:same-fixture\r\nDTSTART;VALUE=DATE:20261101\r\nDTEND;VALUE=DATE:20261102\r\nSUMMARY:Course {name}\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
        return httpx.Response(200, content=content.encode())

    def factory(**kwargs):
        return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)

    for owner, name in [(a, "fixture-a"), (b, "fixture-b")]:
        store.configure(
            owner,
            "moodle",
            {"url": "https://moodle27.braude.ac.il/calendar/export_execute.php?authtoken=" + name},
        )
        store.sync(owner, client_factory=factory)
    assert store.records(a, "moodle")[0]["title"] == "Course fixture-a"
    assert store.records(b, "moodle")[0]["title"] == "Course fixture-b"
    before = store.records(a, "moodle")
    redirect[0] = True
    with pytest.raises(GoogleProblem):
        store.sync(a, client_factory=factory)
    assert store.records(a, "moodle") == before
    assert store.status(a, "moodle")["syncing"] is False
