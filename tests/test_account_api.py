from fastapi.testclient import TestClient


def test_account_api_auth_csrf_and_workspace_isolation(setup_app, monkeypatch):
    monkeypatch.setenv("LIFEOS_ACCOUNT_MODE", "1")
    app = setup_app[2]()
    headers = {"X-LifeOS-Key": "test-process-key"}
    with TestClient(app, base_url="http://127.0.0.1:8000", headers=headers) as left:
        assert left.get("/mode").json()["account_mode"]
        assert (
            left.post("/session", json={"password": "correct horse battery staple"}).status_code
            == 403
        )
        for login in ("api-a", "api-b"):
            assert (
                left.post(
                    "/accounts/register", json={"login": login, "password": "fixture password"}
                ).status_code
                == 201
            )
        signed = left.post(
            "/accounts/session", json={"login": "api-a", "password": "fixture password"}
        )
        assert signed.status_code == 200
        assert "SameSite=lax" in signed.headers["set-cookie"]
        csrf = signed.json()["csrf"]
        root = "/accounts/workspace"
        assert left.post(root + "/tasks", json={"title": "Blocked"}).status_code == 403
        left.headers["X-CSRF-Token"] = csrf
        task = left.post(root + "/tasks", json={"title": "A private task"})
        assert task.status_code == 201
        assert left.get(root + "/assistant/history").status_code == 200
        assert left.get(root + "/review/weekly").status_code == 200
        assert left.get(root + "/notifications").status_code == 200
        assert left.get(root + "/planning/preferences").status_code == 200
        assert left.get(root + "/briefings/schedule").status_code == 200
        assert left.get(root + "/integrations/google/status").status_code == 200
        assert left.get(root + "/integrations/gmail/queue").json() == []
        assert left.get(root + "/push/config").json()["configured"] is False
        assert left.get(root + "/recovery/backups").json() == []
        assert left.get(root + "/recovery/schedule").json()["enabled"] is False
        term = left.post(
            root + "/academic/terms",
            json={"name": "API term", "start_date": "2026-11-01", "end_date": "2027-01-31"},
        ).json()
        batch = left.post(
            root + "/academic/course-batches/preview",
            json={"term_id": term["id"], "rows": [{"name": "API course"}]},
        ).json()
        assert (
            left.post(root + "/academic/course-batches/" + batch["id"] + "/confirm").json()[
                "created_count"
            ]
            == 1
        )
        assert left.get("/tasks").status_code == 403
        token_a = left.cookies.get("lifeos_session")
        signed_b = left.post(
            "/accounts/session", json={"login": "api-b", "password": "fixture password"}
        ).json()
        left.headers["X-CSRF-Token"] = signed_b["csrf"]
        assert left.get(root + "/tasks").json() == []
        assert left.get(root + "/academic/courses").json() == []
        assert (
            left.put(root + "/tasks/" + task.json()["id"], json={"title": "Foreign"}).status_code
            == 404
        )
        left.cookies.set("lifeos_session", token_a, domain="127.0.0.1", path="/")
        left.headers["X-CSRF-Token"] = csrf
        assert left.get(root + "/tasks").json()[0]["title"] == "A private task"
        assert left.delete("/accounts/session").status_code == 204
        assert left.get(root + "/tasks").status_code == 401


def test_account_routes_are_unavailable_in_normal_mode(client):
    assert client.get("/mode").json()["account_mode"] is False
    assert (
        client.post(
            "/accounts/register", json={"login": "disabled", "password": "fixture password"}
        ).status_code
        == 404
    )


def test_http_oauth_callback_requires_initiating_account_and_consumes_state(setup_app, monkeypatch):
    from urllib.parse import parse_qs, urlsplit

    from lifeos.google_calendar import GoogleCalendarService

    monkeypatch.setenv("LIFEOS_ACCOUNT_MODE", "1")
    monkeypatch.setenv("LIFEOS_GOOGLE_CLIENT_ID", "fixture.apps.googleusercontent.com")
    monkeypatch.setenv("LIFEOS_GOOGLE_CLIENT_SECRET", "synthetic secret")
    monkeypatch.setattr(
        GoogleCalendarService,
        "token_request",
        lambda self, values, form: {
            **values,
            "access_token": "synthetic access",
            "refresh_token": "synthetic refresh",
        },
    )
    with TestClient(
        setup_app[2](),
        base_url="http://127.0.0.1:8000",
        headers={"X-LifeOS-Key": "test-process-key"},
    ) as web:
        for name in ("callback-a", "callback-b"):
            web.post("/accounts/register", json={"login": name, "password": "fixture password"})
        signed = web.post(
            "/accounts/session", json={"login": "callback-a", "password": "fixture password"}
        ).json()
        cookie = web.cookies.get("lifeos_session")
        web.headers["X-CSRF-Token"] = signed["csrf"]
        url = web.post("/accounts/workspace/integrations/google/authorize").json()[
            "authorization_url"
        ]
        params = {"state": parse_qs(urlsplit(url).query)["state"][0], "code": "fixture-code"}
        web.post("/accounts/session", json={"login": "callback-b", "password": "fixture password"})
        assert (
            web.get("/accounts/oauth/callback", params=params, follow_redirects=False).status_code
            == 400
        )
        web.cookies.set("lifeos_session", cookie, domain="127.0.0.1", path="/")
        assert (
            web.get("/accounts/oauth/callback", params=params, follow_redirects=False).status_code
            == 303
        )
        assert (
            web.get("/accounts/oauth/callback", params=params, follow_redirects=False).status_code
            == 400
        )
