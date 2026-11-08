import httpx

URL = "https://moodle27.braude.ac.il/calendar/export_execute.php?userid=fixture&authtoken=private-fixture&preset_what=all&preset_time=custom"
ICS = b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//LifeOS Test//EN\r\nBEGIN:VEVENT\r\nUID:deadline\r\nDTSTART:20261027T100000Z\r\nDTEND:20261027T100000Z\r\nSUMMARY:Assignment\r\nURL:https://moodle27.braude.ac.il/mod/assign/view.php?id=123\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"


def test_moodle_configuration_is_private_and_restricts_destinations(client):
    assert client.get("/integrations/moodle/status").status_code == 200
    for url in [
        URL.replace("moodle27.braude.ac.il", "127.0.0.1"),
        URL.replace("https:", "http:"),
        URL.replace("export_execute.php", "other.php"),
    ]:
        assert client.post("/integrations/moodle/config", json={"url": url}).status_code == 422
    assert client.post("/integrations/moodle/config", json={"url": URL}).status_code == 200
    status = client.get("/integrations/moodle/status").json()
    assert status["configured"] and not status["connected"]
    assert "private-fixture" not in str(status) and "authtoken" not in str(status)
    client.headers["X-CSRF-Token"] = "bad"
    assert client.post("/integrations/moodle/disconnect").status_code == 403


def test_moodle_sync_is_atomic_readonly_and_handles_deletions(client, setup_app):
    service = setup_app[0].state.moodle
    client.post("/integrations/moodle/config", json={"url": URL})
    content = ICS
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=content)

    service.http = httpx.Client(transport=httpx.MockTransport(handler))
    assert client.post("/integrations/moodle/sync").status_code == 200
    events = client.get("/integrations/moodle/events").json()
    assert len(events) == 1 and events[0]["source"] == "moodle"
    assert events[0]["end"] > events[0]["start"]
    assert "private-fixture" not in str(events)
    assert all(call.method == "GET" for call in calls)
    content = b"<html>Login required</html>"
    assert client.post("/integrations/moodle/sync").status_code == 502
    assert client.get("/integrations/moodle/events").json() == events
    content = ICS.replace(b"SUMMARY:Assignment", b"SUMMARY:Updated")
    assert client.post("/integrations/moodle/sync").status_code == 200
    assert client.get("/integrations/moodle/events").json()[0]["id"] == events[0]["id"]
    content = b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Test//EN\r\nEND:VCALENDAR\r\n"
    assert client.post("/integrations/moodle/sync").status_code == 200
    assert client.get("/integrations/moodle/events").json() == []
    assert client.post("/integrations/moodle/disconnect").status_code == 200
    assert not client.get("/integrations/moodle/status").json()["configured"]


def test_moodle_parser_date_and_error_semantics():
    import pytest
    from lifeos.moodle import parse_feed

    events = parse_feed(
        ICS.replace(b"DTSTART:20261027T100000Z", b"DTSTART;VALUE=DATE:20261027").replace(
            b"DTEND:20261027T100000Z", b"DTEND;VALUE=DATE:20261028"
        ),
        "moodle27.braude.ac.il",
    )
    assert events[0]["start"] == "2026-10-27" and events[0]["all_day"]
    for content in [
        ICS.replace(b"100000Z", b"100000"),
        ICS.replace(b"SUMMARY:Assignment", b"RRULE:FREQ=DAILY\r\nSUMMARY:Assignment"),
        b"x" * (2 * 1024 * 1024 + 1),
    ]:
        with pytest.raises(Exception):
            parse_feed(content, "moodle27.braude.ac.il")


def test_moodle_never_echoes_invalid_secrets_or_follows_redirects(client, setup_app):
    for body in [{"url": URL + "x" * 9000}, {"url": [URL]}]:
        response = client.post("/integrations/moodle/config", json=body)
        assert response.status_code == 422 and "private-fixture" not in response.text
    client.post("/integrations/moodle/config", json={"url": URL})
    calls = []

    def redirect(request):
        calls.append(request)
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})

    setup_app[0].state.moodle.http = httpx.Client(transport=httpx.MockTransport(redirect))
    assert client.post("/integrations/moodle/sync").status_code == 502
    assert len(calls) == 1
    status = client.get("/integrations/moodle/status").json()
    assert status["state"] == "error" and not status["connected"]


def test_moodle_lease_and_dst_validation(client, setup_app):
    import pytest
    from lifeos.moodle import parse_feed
    from lifeos.moodle_models import MoodleConnection
    from sqlalchemy.orm import Session

    client.post("/integrations/moodle/config", json={"url": URL})
    with Session(setup_app[0].state.moodle.engine) as db:
        row = db.get(MoodleConnection, 1)
        row.lease_owner, row.lease_until = "other-worker", 9999999999
        db.commit()
    assert client.post("/integrations/moodle/sync").status_code == 409
    assert client.post("/integrations/moodle/disconnect").status_code == 409
    assert client.post("/integrations/moodle/config", json={"url": URL}).status_code == 409
    ambiguous = ICS.replace(
        b"DTSTART:20261027T100000Z", b"DTSTART;TZID=Asia/Jerusalem:20261025T013000"
    ).replace(b"DTEND:20261027T100000Z", b"DTEND;TZID=Asia/Jerusalem:20261025T014000")
    with pytest.raises(Exception):
        parse_feed(ambiguous, "moodle27.braude.ac.il")


def test_sync_acquires_lease_before_reading_credentials(client, setup_app, monkeypatch):
    import pytest
    from lifeos.google_calendar import GoogleProblem

    service = setup_app[0].state.moodle
    client.post("/integrations/moodle/config", json={"url": URL})
    decrypt = service.vault.decrypt

    def interleaved(blob):
        with pytest.raises(GoogleProblem):
            service.disconnect()
        with pytest.raises(GoogleProblem):
            service.configure_feed(URL)
        return decrypt(blob)

    monkeypatch.setattr(service.vault, "decrypt", interleaved)
    service.http = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=ICS))
    )
    assert client.post("/integrations/moodle/sync").status_code == 200


def test_compressed_feed_is_rejected_before_reading_body(client, setup_app):
    import gzip

    service = setup_app[0].state.moodle
    client.post("/integrations/moodle/config", json={"url": URL})
    service.http = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, headers={"Content-Encoding": "gzip"}, content=gzip.compress(ICS)
            )
        )
    )
    assert client.post("/integrations/moodle/sync").status_code == 502
    assert (
        client.get("/integrations/moodle/status").json()["error"] == "compressed_feed_not_supported"
    )
