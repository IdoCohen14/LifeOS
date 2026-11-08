import httpx
import pytest
from lifeos.account_braude import AccountBraude, validate_portal_url
from lifeos.accounts import AccountService
from lifeos.google_calendar import GoogleProblem

URL = "https://info.braude.ac.il/yedion/fireflyweb.aspx?prgname=PublicHours&Google_InnerID=123&Google_Token=fixture&Google_Population=S"


def test_portal_url_is_exact_official_subscription_only():
    assert validate_portal_url(URL) == URL
    for bad in (URL.replace("https:", "http:"), URL.replace("info.braude.ac.il", "elsewhere.invalid"),
                URL.replace("PublicHours", "WRITE"), URL + "&Google_Token=other", URL + "#x"):
        with pytest.raises(GoogleProblem):
            validate_portal_url(bad)


def test_portal_owned_sync_read_only_source_and_failed_refresh_preserves_cache(client, setup_app):
    engine = setup_app[0].state.assistant.engine
    accounts = AccountService(engine, enabled=True)
    owner = accounts.register("portal-fixture", "fixture password")
    other = accounts.register("portal-other", "fixture password")
    store = AccountBraude(engine, setup_app[1])
    store.configure(owner, "braude", {"url": URL})
    redirect = [False]

    def handler(request):
        if redirect[0]:
            return httpx.Response(302, headers={"Location": "https://elsewhere.invalid"})
        return httpx.Response(200, content=b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nREFRESH-INTERVAL;VALUE=DURATION:P6H\r\nX-PUBLISHED-TTL:P6H\r\nBEGIN:VEVENT\r\nUID:fixture\r\nDTSTART:20261101T080000Z\r\nDTEND:20261101T090000Z\r\nSUMMARY:Fixture class\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")

    def factory(**kwargs):
        return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)

    store.sync(owner, client_factory=factory)
    records = store.records(owner, "braude")
    assert records[0]["source"] == "braude"
    assert records[0]["source_url"] == "https://info.braude.ac.il/"
    assert store.records(other, "braude") == []
    assert "fixture" not in records[0]["source_url"]
    redirect[0] = True
    with pytest.raises(GoogleProblem):
        store.sync(owner, client_factory=factory)
    assert store.records(owner, "braude") == records
    assert not store.status(owner, "braude")["syncing"]
