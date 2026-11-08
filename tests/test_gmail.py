import httpx


def test_gmail_oauth_is_separate_and_readonly(client, setup_app):
    from urllib.parse import parse_qs, urlparse

    app, _, _ = setup_app
    app.state.google.configure("fixture.apps.googleusercontent.com", "fixture-secret")
    assert client.get("/integrations/gmail/status").json()["configured"]
    response = client.post("/integrations/gmail/authorize")
    assert response.status_code == 200
    params = parse_qs(urlparse(response.json()["authorization_url"]).query)
    assert params["scope"] == ["https://www.googleapis.com/auth/gmail.readonly"]
    assert params["state"][0].startswith("gmail.")
    assert params["code_challenge_method"] == ["S256"]
    app.state.gmail.http = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "access_token": "gmail-access",
                    "refresh_token": "gmail-refresh",
                    "scope": "https://www.googleapis.com/auth/gmail.readonly",
                },
            )
        )
    )
    callback = client.get(
        "/integrations/google/callback",
        params={"state": params["state"][0], "code": "code"},
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert client.get("/integrations/gmail/status").json()["connected"]
    assert not client.get("/integrations/google/status").json()["connected"]
    assert (
        client.get(
            "/integrations/google/callback",
            params={"state": params["state"][0], "code": "code"},
            follow_redirects=False,
        ).status_code
        == 400
    )


def connect(app):
    from lifeos.gmail_models import GmailConnection
    from sqlalchemy.orm import Session

    service = app.state.gmail
    with Session(service.engine) as db:
        db.add(
            GmailConnection(
                id=1,
                credentials=service.vault.encrypt(
                    {
                        "client_id": "fixture.apps.googleusercontent.com",
                        "client_secret": "secret",
                        "access_token": "access",
                        "refresh_token": "refresh",
                        "expires_at": 9999999999,
                    }
                ),
                state="connected",
            )
        )
        db.commit()
    return service


def test_gmail_snapshot_is_safe_readonly_and_atomic(client, setup_app):
    service = connect(setup_app[0])
    calls = []
    ids = ["abc123"]
    fail = False

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/profile"):
            return httpx.Response(200, json={"emailAddress": "account@example.test"})
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": id} for id in ids]})
        if fail:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "id": "abc123",
                "threadId": "thread123",
                "internalDate": "1792920000000",
                "labelIds": ["INBOX", "UNREAD", "IMPORTANT", "CATEGORY_PERSONAL"],
                "snippet": "<img src=x onerror=alert(1)>",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "שלום"},
                        {"name": "From", "value": "sender@example.test"},
                    ]
                },
            },
        )

    service.http = httpx.Client(transport=httpx.MockTransport(handler))
    assert client.post("/integrations/gmail/sync").status_code == 200
    messages = client.get("/integrations/gmail/messages").json()
    assert messages[0]["subject"] == "שלום"
    assert messages[0]["unread"] and messages[0]["important"]
    assert all(call.method == "GET" for call in calls)
    assert "access" not in str(messages)
    fail = True
    assert client.post("/integrations/gmail/sync").status_code == 502
    assert client.get("/integrations/gmail/messages").json() == messages
    ids.clear()
    assert client.post("/integrations/gmail/sync").status_code == 200
    assert client.get("/integrations/gmail/messages").json() == []
    assert client.post("/integrations/gmail/disconnect").status_code == 200
    assert not client.get("/integrations/gmail/status").json()["connected"]


def test_gmail_errors_and_lease_preserve_calendar_and_session(client, setup_app):
    from lifeos.gmail_models import GmailConnection
    from sqlalchemy.orm import Session

    service = connect(setup_app[0])
    service.http = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(429)))
    assert client.post("/integrations/gmail/sync").status_code == 502
    status = client.get("/integrations/gmail/status").json()
    assert status["state"] == "error" and status["error"] == "rate_limited"
    assert status["next_sync"] > 0
    service.http = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(401)))
    assert client.post("/integrations/gmail/sync").status_code == 409
    assert client.get("/integrations/gmail/status").json()["state"] == "expired"
    assert client.get("/session").status_code == 200
    with Session(service.engine) as db:
        row = db.get(GmailConnection, 1)
        row.lease_owner, row.lease_until = "other-worker", 9999999999
        db.commit()
    assert client.post("/integrations/gmail/sync").status_code == 409
    assert client.post("/integrations/gmail/disconnect").status_code == 409


def test_gmail_missing_scope_and_forged_callback_never_connect(client, setup_app):
    from urllib.parse import parse_qs, urlparse

    app = setup_app[0]
    app.state.google.configure("fixture.apps.googleusercontent.com", "fixture-secret")
    response = client.post("/integrations/gmail/authorize")
    state = parse_qs(urlparse(response.json()["authorization_url"]).query)["state"][0]
    app.state.gmail.http = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"access_token": "access", "refresh_token": "refresh", "scope": "email"}
            )
        )
    )
    result = client.get(
        "/integrations/google/callback",
        params={"state": state, "code": "code"},
        follow_redirects=False,
    )
    assert result.status_code == 303 and "error" in result.headers["location"]
    assert not client.get("/integrations/gmail/status").json()["connected"]
    assert (
        client.get(
            "/integrations/google/callback?state=gmail.forged&code=code", follow_redirects=False
        ).status_code
        == 400
    )


def test_background_sync_acknowledges_without_waiting_for_provider(client, setup_app):
    service = connect(setup_app[0])
    # The production response is sent before BackgroundTasks runs; TestClient drains it.
    service.http = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(429)))
    response = client.post("/integrations/gmail/sync?background=true")
    assert response.status_code == 202 and response.json() == {"queued": True}
    assert client.get("/integrations/gmail/status").json()["error"] == "rate_limited"
