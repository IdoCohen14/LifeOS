import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def setup_app(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFEOS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIFEOS_API_KEY", "test-process-key")
    from lifeos.main import create_app
    from lifeos.security import initialize_password

    initialize_password(tmp_path, "correct horse battery staple")
    app = create_app()
    return app, tmp_path, create_app


@pytest.fixture
def client(setup_app):
    app, _, _ = setup_app
    with TestClient(
        app, base_url="http://127.0.0.1:8000", headers={"X-LifeOS-Key": "test-process-key"}
    ) as c:
        r = c.post("/session", json={"password": "correct horse battery staple"})
        assert r.status_code == 200
        c.headers["X-CSRF-Token"] = r.json()["csrf"]
        yield c
