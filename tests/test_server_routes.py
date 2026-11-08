from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient


def test_server_uses_https_cookie_callback_and_owned_routes(setup_app, monkeypatch):
    monkeypatch.setenv("LIFEOS_DEPLOYMENT_MODE", "server")
    monkeypatch.setenv("LIFEOS_PUBLIC_ORIGIN", "https://lifeos.example")
    monkeypatch.setenv("LIFEOS_TEST_MODE", "1")
    monkeypatch.setenv("LIFEOS_GOOGLE_CLIENT_ID", "fixture.apps.googleusercontent.com")
    monkeypatch.setenv("LIFEOS_GOOGLE_CLIENT_SECRET", "synthetic secret")
    app = setup_app[2]()
    with TestClient(app, base_url="https://127.0.0.1:8000", headers={"X-LifeOS-Key": "test-process-key", "Origin": "https://lifeos.example"}) as web:
        assert web.get("/mode").json()["account_mode"]
        assert web.post("/accounts/register", json={"login": "server-fixture", "password": "fixture password"}).status_code == 201
        response = web.post("/accounts/session", json={"login": "server-fixture", "password": "fixture password"})
        assert response.status_code == 200
        assert "; Secure" in response.headers["set-cookie"]
        web.headers["X-CSRF-Token"] = response.json()["csrf"]
        authorized = web.post("/accounts/workspace/integrations/google/authorize")
        assert authorized.status_code == 200
        assert "; Secure" in authorized.headers["set-cookie"]
        url = authorized.json()["authorization_url"]
        assert parse_qs(urlsplit(url).query)["redirect_uri"] == ["https://lifeos.example/api/accounts/oauth/callback"]
        assert web.get("/tasks").status_code == 403
        assert web.get("/accounts/workspace/tasks").json() == []
        assert web.get("/accounts/workspace/assistant/help").status_code == 200
        assert web.get("/accounts/workspace/assistant/status").json()["state"] == "disabled_on_server"
        web.headers["Origin"] = "http://127.0.0.1:3000"
        assert web.get("/accounts/workspace/tasks").status_code == 403
