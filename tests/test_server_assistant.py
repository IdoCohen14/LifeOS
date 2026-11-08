import httpx
import pytest
from fastapi import HTTPException
from lifeos.assistant import AssistantService
from lifeos.deployment import DeploymentConfig


def test_server_profile_never_contacts_model(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFEOS_DEPLOYMENT_MODE", "server")
    monkeypatch.setenv("LIFEOS_PUBLIC_ORIGIN", "https://lifeos.example")
    monkeypatch.setenv("LIFEOS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIFEOS_TEST_MODE", "1")
    service = AssistantService(None, None, None)
    calls = []
    service.http.close()
    service.http = httpx.Client(transport=httpx.MockTransport(lambda request: calls.append(request) or httpx.Response(500)))
    try:
        assert service.status()["state"] == "disabled_on_server"
        with pytest.raises(HTTPException) as error:
            service.infer({})
        assert error.value.status_code == 503 and calls == []
    finally:
        service.http.close()


def test_private_assistant_is_explicit_single_owner_only(tmp_path, monkeypatch):
    owner = "00000000-0000-4000-8000-000000000001"
    values = {"LIFEOS_DEPLOYMENT_MODE": "server", "LIFEOS_PUBLIC_ORIGIN": "https://demo.ts.net",
              "LIFEOS_DATA_DIR": str(tmp_path), "LIFEOS_TEST_MODE": "1",
              "LIFEOS_PILOT_OWNER_ID": owner, "LIFEOS_PRIVATE_PC_ASSISTANT": "1"}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    config = DeploymentConfig.from_env()
    assert config.assistant_enabled
    for account_id in (None, "other", owner):
        service = AssistantService(None, None, None, account_id=account_id)
        try:
            # None is the existing shared model transport, not a data workspace.
            assert service.inference_enabled == (account_id in (None, owner))
        finally:
            service.http.close()
    for changes in ({"LIFEOS_PILOT_OWNER_ID": ""}, {"LIFEOS_PUBLIC_ORIGIN": "https://lifeos.example"},
                    {"LIFEOS_PRIVATE_PC_ASSISTANT": "yes"}):
        with pytest.raises(ValueError):
            DeploymentConfig.from_env({**values, **changes})


def test_private_pilot_routes_use_shared_model_but_keep_data_and_commit_owned(client, setup_app, monkeypatch):
    from fastapi.testclient import TestClient
    from lifeos.accounts import AccountService

    engine = setup_app[0].state.assistant.engine
    auth = AccountService(engine, enabled=True)
    owner = auth.register("private-owner", "fixture password")
    auth.register("other-owner", "fixture password")
    for key, value in {"LIFEOS_DEPLOYMENT_MODE": "server", "LIFEOS_PUBLIC_ORIGIN": "https://demo.ts.net",
                       "LIFEOS_TEST_MODE": "1", "LIFEOS_PILOT_OWNER_ID": owner,
                       "LIFEOS_PRIVATE_PC_ASSISTANT": "1"}.items():
        monkeypatch.setenv(key, value)
    app = setup_app[2]()
    transport = app.state.assistant
    transport.http.close()
    transport.http = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200,
        json={"models": [{"name": "qwen3:4b"}]} if request.method == "GET" else
        {"message": {"content": '{"action":"task","title":"Fixture proposal","date":"2026-11-15"}'}})))
    with TestClient(app, base_url="https://127.0.0.1:8000", headers={"X-LifeOS-Key": "test-process-key", "Origin": "https://demo.ts.net"}) as web:
        assert web.get("/accounts/workspace/assistant/status").status_code == 401
        assert web.post("/accounts/session", json={"login": "other-owner", "password": "fixture password"}).status_code in (401, 403)
        login = web.post("/accounts/session", json={"login": "private-owner", "password": "fixture password"})
        assert login.status_code == 200
        web.headers["X-CSRF-Token"] = login.json()["csrf"]
        assert web.get("/accounts/workspace/assistant/status").json()["ready"]
        assert web.get("/assistant/status").status_code == 403
        result = web.post("/accounts/workspace/assistant/chat", json={"message": "Add a task on 2026-11-15"})
        assert result.status_code == 200 and result.json()["proposal"]
        assert web.get("/accounts/workspace/tasks").json() == []
