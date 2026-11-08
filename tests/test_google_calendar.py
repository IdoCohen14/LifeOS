import httpx
import pytest


@pytest.fixture(autouse=True)
def google_test_mode(monkeypatch):
    monkeypatch.setenv("LIFEOS_TEST_MODE", "1")


def test_configuration_endpoint_is_not_public(client, monkeypatch):
    monkeypatch.delenv("LIFEOS_TEST_MODE")
    assert configure(client).status_code == 404


def test_oversized_provider_response_preserves_cached_events(client, setup_app, monkeypatch):
    connect_fixture(client, setup_app, monkeypatch)
    service = setup_app[0].state.google
    assert client.post("/integrations/google/sync").status_code == 200
    cached = client.get("/integrations/google/events").json()

    class Oversized(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(257):
                yield b"x" * 65536
            raise AssertionError("Stream must stop when the limit is crossed")

    service.http = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=Oversized()))
    )
    assert client.post("/integrations/google/sync").status_code == 502
    assert (
        client.get("/integrations/google/status").json()["error"] == "provider_response_too_large"
    )
    assert client.get("/integrations/google/events").json() == cached


@pytest.mark.parametrize("limit", ["download", "existing", "staged", "timeout", "write_timeout"])
def test_calendar_total_budgets_preserve_cache_and_checkpoint(
    client, setup_app, monkeypatch, limit
):
    from lifeos.google_models import GoogleCalendar
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    connect_fixture(client, setup_app, monkeypatch)
    service = setup_app[0].state.google
    assert client.post("/integrations/google/sync").status_code == 200
    cached = client.get("/integrations/google/events").json()
    with Session(service.engine) as db:
        checkpoint = db.scalar(select(GoogleCalendar.sync_token))
    monkeypatch.setattr(
        "lifeos.google_calendar.MAX_SYNC_BYTES", 1024 if limit == "download" else 32 * 1024 * 1024
    )
    monkeypatch.setattr(
        "lifeos.google_calendar.MAX_CACHE_BYTES",
        1 if limit == "existing" else (1024 * 1024 if limit == "write_timeout" else 2048),
    )
    tick = [0]
    if limit in {"timeout", "write_timeout"}:
        import time
        from types import SimpleNamespace

        monkeypatch.setattr(
            "lifeos.google_calendar.time",
            SimpleNamespace(time=time.time, monotonic=lambda: tick[0]),
        )
    if limit == "timeout":
        original = service._request

        def delayed(*args, **kwargs):
            response = original(*args, **kwargs)
            tick[0] = 121
            return response

        monkeypatch.setattr(service, "_request", delayed)
    if limit == "write_timeout":
        from sqlalchemy import event

        def delayed_insert(connection, cursor, statement, parameters, context, executemany):
            if statement.startswith("INSERT INTO google_records"):
                tick[0] = 121

        event.listen(service.engine, "before_cursor_execute", delayed_insert)
    pages = []

    def handler(request):
        if request.url.path.endswith("calendarList"):
            return httpx.Response(200, json={"items": [{"id": "primary", "primary": True}]})
        page = int(request.url.params.get("pageToken", "0"))
        pages.append(page)
        event = {
            "id": "large-" + str(page),
            "description": "x" * (400 if limit == "download" else 3000),
            "start": {"dateTime": "2026-10-25T10:00:00+02:00"},
            "end": {"dateTime": "2026-10-25T11:00:00+02:00"},
        }
        response = httpx.Response(
            200,
            json={
                "items": [event],
                **(
                    {"nextPageToken": str(page + 1)}
                    if limit == "download" and page < 3
                    else {"nextSyncToken": "new"}
                ),
            },
        )
        if limit == "download":
            assert len(response.content) < 1024
        return response

    service.http = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        assert client.post("/integrations/google/sync").status_code == 409
    finally:
        if limit == "write_timeout":
            event.remove(service.engine, "before_cursor_execute", delayed_insert)
    expected = (
        "calendar_sync_timeout"
        if limit in {"timeout", "write_timeout"}
        else (
            "calendar_download_limit_exceeded"
            if limit == "download"
            else "calendar_cache_limit_exceeded"
        )
    )
    assert client.get("/integrations/google/status").json()["error"] == expected
    if limit == "download":
        assert len(pages) >= 2
    assert client.get("/integrations/google/events").json() == cached
    with Session(service.engine) as db:
        assert db.scalar(select(GoogleCalendar.sync_token)) == checkpoint


def configure(client):
    return client.post(
        "/integrations/google/config",
        json={
            "client_id": "test.apps.googleusercontent.com",
            "client_secret": "test-client-secret",
        },
    )


def test_google_setup_is_private_and_callback_validates_state(client):
    assert client.get("/integrations/google/status").status_code == 200
    assert client.get("/integrations/google/status").json()["connected"] is False
    assert configure(client).status_code == 200
    status = client.get("/integrations/google/status").json()
    assert status["configured"] is True
    assert "test-client-secret" not in str(status)
    assert (
        client.get(
            "/integrations/google/callback?state=forged&code=bad", follow_redirects=False
        ).status_code
        == 400
    )
    client.headers["X-CSRF-Token"] = ""
    assert configure(client).status_code == 403


def connect_fixture(client, setup_app, monkeypatch):
    from urllib.parse import parse_qs, urlparse

    app, _, _ = setup_app
    configure(client)
    monkeypatch.setattr("webbrowser.open", lambda *_: True)
    calls = []
    payloads = {
        "first": {
            "items": [
                {
                    "id": "a",
                    "summary": "Meeting",
                    "start": {"dateTime": "2026-10-25T10:00:00+02:00"},
                    "end": {"dateTime": "2026-10-25T11:00:00+02:00"},
                    "htmlLink": "https://www.google.com/calendar/event?eid=a",
                }
            ],
            "nextSyncToken": "s1",
        },
        "s1": {"items": [{"id": "a", "status": "cancelled"}], "nextSyncToken": "s2"},
    }

    def handler(request):
        calls.append(request)
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(
                200,
                json={
                    "access_token": "access-secret",
                    "refresh_token": "refresh-secret",
                    "expires_in": 3600,
                    "scope": "https://www.googleapis.com/auth/calendar.events.readonly https://www.googleapis.com/auth/calendar.calendarlist.readonly",
                },
            )
        if request.url.path.endswith("/users/me/calendarList"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "primary@example.test",
                            "summary": "Personal",
                            "primary": True,
                            "timeZone": "Asia/Jerusalem",
                        }
                    ]
                },
            )
        if request.url.path.endswith("/events"):
            return httpx.Response(200, json=payloads[request.url.params.get("syncToken", "first")])
        return httpx.Response(404)

    app.state.google.http = httpx.Client(transport=httpx.MockTransport(handler))
    response = client.post("/integrations/google/authorize")
    assert response.status_code == 200
    query = parse_qs(urlparse(response.json()["authorization_url"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert "readonly" in query["scope"][0]
    state = query["state"][0]
    callback = client.get(
        "/integrations/google/callback",
        params={"state": state, "code": "test-code"},
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert (
        client.get(
            "/integrations/google/callback",
            params={"state": state, "code": "test-code"},
            follow_redirects=False,
        ).status_code
        == 400
    )
    return app.state.google, calls, payloads


def test_sync_upserts_deletes_and_never_mutates_google_events(client, setup_app, monkeypatch):
    service, calls, payloads = connect_fixture(client, setup_app, monkeypatch)
    assert client.post("/integrations/google/sync").status_code == 200
    events = client.get("/integrations/google/events").json()
    assert len(events) == 1 and events[0]["start"] == "2026-10-25T08:00:00Z"
    assert events[0]["source"] == "google"
    assert client.post("/integrations/google/sync").status_code == 200
    assert client.get("/integrations/google/events").json() == []
    assert all(
        request.method == "GET" for request in calls if request.url.host == "www.googleapis.com"
    )
    assert client.post("/integrations/google/disconnect").status_code == 200
    assert client.get("/integrations/google/status").json()["connected"] is False


def test_failed_pagination_keeps_checkpoint_and_cached_events(client, setup_app, monkeypatch):
    service, _, _ = connect_fixture(client, setup_app, monkeypatch)
    client.post("/integrations/google/sync")

    def fail(request):
        if request.url.path.endswith("/users/me/calendarList"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"id": "primary@example.test", "summary": "Personal", "primary": True}
                    ]
                },
            )
        if not request.url.params.get("pageToken"):
            return httpx.Response(
                200, json={"items": [{"id": "a", "status": "cancelled"}], "nextPageToken": "p2"}
            )
        return httpx.Response(503)

    service.http = httpx.Client(transport=httpx.MockTransport(fail))
    assert client.post("/integrations/google/sync").status_code == 502
    assert len(client.get("/integrations/google/events").json()) == 1
    assert client.get("/integrations/google/status").json()["error"] == "provider_unavailable"


def test_expired_sync_token_recovers_without_duplicates(client, setup_app, monkeypatch):
    service, _, _ = connect_fixture(client, setup_app, monkeypatch)
    client.post("/integrations/google/sync")
    original = service.http

    def recover(request):
        if request.url.params.get("syncToken"):
            return httpx.Response(410)
        return original._transport.handle_request(request)

    service.http = httpx.Client(transport=httpx.MockTransport(recover))
    for _ in range(2):
        assert client.post("/integrations/google/sync").status_code == 200
        assert len(client.get("/integrations/google/events").json()) == 1


def test_recurring_instances_all_day_and_encryption(client, setup_app, monkeypatch):
    from lifeos.google_models import GoogleConnection
    from sqlalchemy.orm import Session

    service, _, payloads = connect_fixture(client, setup_app, monkeypatch)
    master = {
        "id": "series",
        "recurrence": ["RRULE:FREQ=DAILY"],
        "start": {"date": "2026-10-25"},
        "end": {"date": "2026-10-26"},
    }
    payloads["first"] = {"items": [master], "nextSyncToken": "series-token"}
    original = service.http

    def instances(request):
        if request.url.path.endswith("/instances"):
            assert "timeMin" in request.url.params and "timeMax" in request.url.params
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "instance1",
                            "summary": "Holiday",
                            "start": {"date": "2026-10-25"},
                            "end": {"date": "2026-10-26"},
                        }
                    ]
                },
            )
        return original._transport.handle_request(request)

    service.http = httpx.Client(transport=httpx.MockTransport(instances))
    assert client.post("/integrations/google/sync").status_code == 200
    event = client.get("/integrations/google/events").json()[0]
    assert event["all_day"] is True and event["start"] == "2026-10-25"
    with Session(service.engine) as db:
        row = db.get(GoogleConnection, 1)
        assert b"refresh-secret" not in row.credentials
        assert service.vault.decrypt(row.credentials)["refresh_token"] == "refresh-secret"


def test_revoked_credentials_preserve_cache_and_local_session(client, setup_app, monkeypatch):
    from lifeos.google_models import GoogleConnection
    from sqlalchemy.orm import Session

    service, _, _ = connect_fixture(client, setup_app, monkeypatch)
    client.post("/integrations/google/sync")
    with Session(service.engine) as db:
        row = db.get(GoogleConnection, 1)
        values = service.vault.decrypt(row.credentials)
        values["expires_at"] = 0
        row.credentials = service.vault.encrypt(values)
        db.commit()
    service.http = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(400, json={"error": "invalid_grant"})
        )
    )
    assert client.post("/integrations/google/sync").status_code == 409
    assert client.get("/integrations/google/status").json()["state"] == "expired"
    assert client.get("/session").status_code == 200
    assert len(client.get("/integrations/google/events").json()) == 1


def test_active_lease_prevents_overlapping_sync_and_config_changes(client, setup_app, monkeypatch):
    import time

    from lifeos.google_models import GoogleConnection
    from sqlalchemy.orm import Session

    service, _, _ = connect_fixture(client, setup_app, monkeypatch)
    with Session(service.engine) as db:
        row = db.get(GoogleConnection, 1)
        row.lease_owner = "other-worker"
        row.lease_until = int(time.time()) + 300
        db.commit()
    assert client.post("/integrations/google/sync").status_code == 409
    assert configure(client).status_code == 409


def test_provider_quota_error_is_retryable_not_reauthorization(client, setup_app, monkeypatch):
    service, _, _ = connect_fixture(client, setup_app, monkeypatch)
    service.http = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                403, json={"error": {"errors": [{"reason": "userRateLimitExceeded"}]}}
            )
        )
    )
    assert client.post("/integrations/google/sync").status_code == 502
    status = client.get("/integrations/google/status").json()
    assert status["state"] == "error"
    assert status["error"] == "rate_limited"
    assert status["next_sync"] > 0
