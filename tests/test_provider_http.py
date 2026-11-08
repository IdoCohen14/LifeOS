import httpx
import pytest
from lifeos.google_calendar import GoogleProblem


class FixtureStream(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.reads = 0
        self.closed = False

    def __iter__(self):
        for chunk in self.chunks:
            self.reads += 1
            yield chunk

    def close(self):
        self.closed = True


def test_google_response_limit_stops_stream_and_closes_it(setup_app):
    service = setup_app[0].state.google
    stream = FixtureStream([b"x" * 65536] * 4)
    service.http = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers={"Content-Length": "1"}, stream=stream)
        )
    )
    with pytest.raises(GoogleProblem) as error:
        service._request("GET", "https://www.googleapis.com/calendar/v3/test", max_bytes=65536)
    assert error.value.code == "provider_response_too_large"
    assert stream.reads == 2 and stream.closed


@pytest.mark.parametrize("kind", ["redirect", "compressed", "untrusted"])
def test_provider_transport_rejects_unsafe_responses_or_destinations(setup_app, kind):
    service = setup_app[0].state.google
    calls = []
    stream = FixtureStream([b"fixture-secret"])

    def handler(request):
        calls.append(request)
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(
            302 if kind == "redirect" else 200,
            headers={
                "Location": "http://127.0.0.1:9999/private",
                **({"Content-Encoding": "gzip"} if kind == "compressed" else {}),
            },
            stream=stream,
        )

    service.http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    url = (
        "http://127.0.0.1:9999/private"
        if kind == "untrusted"
        else "https://gmail.googleapis.com/gmail/v1/users/me/profile"
    )
    with pytest.raises(GoogleProblem) as error:
        service._request("GET", url, headers={"Authorization": "Bearer fixture-secret"})
    assert "fixture-secret" not in str(error.value)
    assert len(calls) == (0 if kind == "untrusted" else 1)
    if calls:
        assert stream.reads == 0 and stream.closed


def test_small_token_response_and_refresh_use_bounded_transport(setup_app):
    service = setup_app[0].state.google
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"access_token": "fixture-token", "expires_in": 3600})

    service.http = httpx.Client(transport=httpx.MockTransport(handler))
    result = service.token_request(
        {"client_id": "fixture-id", "client_secret": "fixture-secret"},
        {"refresh_token": "fixture-refresh", "grant_type": "refresh_token"},
    )
    assert result["access_token"] == "fixture-token"
    assert len(seen) == 1 and seen[0].headers["accept-encoding"] == "identity"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.googleapis.com.evil.test/calendar/v3",
        "https://fixture-secret@www.googleapis.com/calendar/v3",
        "https://www.googleapis.com:444/calendar/v3",
        "http://www.googleapis.com/calendar/v3",
        "https://www.googleapis.com/calendar/v3#fragment",
        "https://www.googleapis.com:invalid/calendar/v3",
    ],
)
def test_provider_endpoint_allowlist_rejects_before_network(setup_app, url):
    service = setup_app[0].state.google

    def forbidden(request):
        pytest.fail("Untrusted destination must not reach transport")

    service.http = httpx.Client(transport=httpx.MockTransport(forbidden))
    with pytest.raises(GoogleProblem) as error:
        service._request("GET", url)
    assert error.value.code == "invalid_provider_endpoint"
    assert "fixture-secret" not in str(error.value)


@pytest.mark.parametrize("empty", [False, True])
def test_provider_read_deadline_closes_stream(setup_app, monkeypatch, empty):
    import time
    from types import SimpleNamespace

    service = setup_app[0].state.google
    tick = [0]

    class SlowStream(FixtureStream):
        def __iter__(self):
            tick[0] = 31
            if not empty:
                yield b"x"

    stream = SlowStream([])
    monkeypatch.setattr(
        "lifeos.google_calendar.time", SimpleNamespace(time=time.time, monotonic=lambda: tick[0])
    )
    service.http = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream))
    )
    with pytest.raises(GoogleProblem) as error:
        service._request("GET", "https://www.googleapis.com/calendar/v3/test")
    assert error.value.code == "provider_response_timeout" and stream.closed


def test_token_exchange_has_smaller_response_limit(setup_app):
    service = setup_app[0].state.google
    stream = FixtureStream([b"x" * 65536] * 4)
    service.http = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream))
    )
    with pytest.raises(GoogleProblem) as error:
        service.token_request(
            {"client_id": "fixture-id", "client_secret": "fixture-secret"},
            {"refresh_token": "fixture-refresh", "grant_type": "refresh_token"},
        )
    assert error.value.code == "provider_response_too_large"
    assert stream.reads == 3 and stream.closed
